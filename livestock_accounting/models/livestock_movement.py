from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LivestockMovement(models.Model):
    _name = "livestock.movement"
    _description = "Movimientos masivos del hato"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, readonly=True, default=lambda self: _("Nuevo"))
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today, tracking=True)
    movement_type = fields.Selection(
        [
            ("weight", "Registro masivo de peso"),
            ("health", "Registro masivo de sanidad"),
            ("retirement", "Baja masiva del hato"),
            ("reclassification", "Reclasificación de categoría"),
        ],
        string="Tipo de movimiento",
        required=True,
        default="weight",
        tracking=True,
    )
    cattle_ids = fields.Many2many(
        "livestock.cattle",
        string="Ganado",
        domain="[('state', '=', 'inventory')]",
        tracking=True,
    )
    notes = fields.Text(string="Notas del movimiento")
    state = fields.Selection(
        [("draft", "Borrador"), ("applied", "Aplicado")],
        string="Estado",
        required=True,
        default="draft",
        tracking=True,
    )

    weight_line_ids = fields.One2many(
        "livestock.movement.weight.line",
        "movement_id",
        string="Detalle de pesos",
    )
    health_event_type = fields.Selection(
        [
            ("vacuna", "Vacunación"),
            ("tratamiento", "Tratamiento"),
            ("revision", "Revisión veterinaria"),
            ("bienestar", "Bienestar / manejo"),
        ],
        string="Tipo de evento sanitario",
    )
    health_description = fields.Char(string="Descripción sanitaria")
    health_veterinarian = fields.Char(string="Veterinario / responsable")
    retirement_reason = fields.Selection(
        [
            ("muerte", "Muerte"),
            ("enfermedad", "Enfermedad"),
            ("accidente", "Accidente"),
            ("venta", "Venta"),
            ("otro", "Otro"),
        ],
        string="Motivo de baja",
    )
    retirement_notes = fields.Text(string="Notas de baja")
    new_category_id = fields.Many2one("livestock.category", string="Nueva categoría")

    movement_history_ids = fields.One2many(
        "livestock.movement.history",
        "movement_id",
        string="Histórico generado",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo")) == _("Nuevo"):
                vals["name"] = self.env["ir.sequence"].next_by_code("livestock.movement") or _("Nuevo")
        return super().create(vals_list)

    @api.constrains("movement_type", "weight_line_ids", "health_event_type", "health_description", "retirement_reason", "new_category_id")
    def _check_required_by_type(self):
        for movement in self:
            if movement.movement_type == "weight":
                if not movement.weight_line_ids:
                    raise UserError(_("Debe registrar al menos una línea de peso."))
                invalid_lines = movement.weight_line_ids.filtered(lambda line: line.weight <= 0)
                if invalid_lines:
                    raise UserError(_("Todas las líneas de peso deben ser mayores que cero."))
            if movement.movement_type == "health":
                if not movement.health_event_type or not movement.health_description:
                    raise UserError(_("Debe indicar tipo y descripción para el registro sanitario masivo."))
            if movement.movement_type == "retirement" and not movement.retirement_reason:
                raise UserError(_("Debe indicar el motivo para la baja masiva."))
            if movement.movement_type == "reclassification" and not movement.new_category_id:
                raise UserError(_("Debe indicar la nueva categoría para la reclasificación."))

    def action_apply(self):
        for movement in self:
            if movement.state == "applied":
                raise UserError(_("El movimiento %s ya fue aplicado.") % movement.name)
            target_cattle = movement.cattle_ids
            if movement.movement_type == "weight":
                target_cattle = movement.weight_line_ids.mapped("cattle_id")
                movement.cattle_ids = [fields.Command.set(target_cattle.ids)]
            if not target_cattle:
                raise UserError(_("Debe seleccionar al menos un animal."))
            movement._apply_to_cattle()
            movement.state = "applied"

    def _apply_to_cattle(self):
        self.ensure_one()
        history_values = []
        target_cattle = self.cattle_ids
        weight_by_cattle_id = {}
        if self.movement_type == "weight":
            target_cattle = self.weight_line_ids.mapped("cattle_id")
            weight_by_cattle_id = {line.cattle_id.id: line.weight for line in self.weight_line_ids}

        for cattle in target_cattle:
            vals = {
                "movement_id": self.id,
                "cattle_id": cattle.id,
                "date": self.date,
                "movement_type": self.movement_type,
                "notes": self.notes,
                "from_category_id": cattle.category_id.id,
                "from_state": cattle.state,
            }

            if self.movement_type == "weight":
                weight = weight_by_cattle_id.get(cattle.id, 0.0)
                self.env["livestock.weight.control"].create(
                    {
                        "cattle_id": cattle.id,
                        "date": self.date,
                        "weight": weight,
                        "notes": self.notes,
                    }
                )
                vals.update({"weight": weight})

            elif self.movement_type == "health":
                self.env["livestock.health.event"].create(
                    {
                        "cattle_id": cattle.id,
                        "date": self.date,
                        "event_type": self.health_event_type,
                        "description": self.health_description,
                        "veterinarian": self.health_veterinarian,
                        "notes": self.notes,
                    }
                )
                vals.update(
                    {
                        "health_event_type": self.health_event_type,
                        "health_description": self.health_description,
                        "health_veterinarian": self.health_veterinarian,
                    }
                )

            elif self.movement_type == "retirement":
                cattle.write(
                    {
                        "state": "retired",
                        "retirement_reason": self.retirement_reason,
                        "retirement_notes": self.retirement_notes or self.notes,
                    }
                )
                vals.update(
                    {
                        "retirement_reason": self.retirement_reason,
                        "retirement_notes": self.retirement_notes or self.notes,
                    }
                )

            elif self.movement_type == "reclassification":
                if cattle.category_id == self.new_category_id:
                    continue
                cattle.category_id = self.new_category_id
                vals.update({"to_category_id": self.new_category_id.id})

            vals.update({"to_category_id": cattle.category_id.id, "to_state": cattle.state})
            history_values.append(vals)

        for values in history_values:
            self.env["livestock.movement.history"].create(values)


class LivestockMovementHistory(models.Model):
    _name = "livestock.movement.history"
    _description = "Histórico de movimientos del ganado"
    _order = "date desc, id desc"

    movement_id = fields.Many2one("livestock.movement", string="Movimiento", required=True, ondelete="cascade")
    cattle_id = fields.Many2one("livestock.cattle", string="Ganado", required=True, ondelete="cascade")
    date = fields.Date(string="Fecha", required=True)
    movement_type = fields.Selection(
        [
            ("weight", "Registro masivo de peso"),
            ("health", "Registro masivo de sanidad"),
            ("retirement", "Baja masiva del hato"),
            ("reclassification", "Reclasificación de categoría"),
        ],
        string="Tipo",
        required=True,
    )
    notes = fields.Text(string="Notas")
    from_category_id = fields.Many2one(
        "livestock.category",
        string="Categoría anterior",
    )
    to_category_id = fields.Many2one(
        "livestock.category",
        string="Categoría nueva",
    )
    from_state = fields.Selection(
        [("inventory", "En inventario"), ("retired", "Dado de baja"), ("sold", "Vendido")],
        string="Estado anterior",
    )
    to_state = fields.Selection(
        [("inventory", "En inventario"), ("retired", "Dado de baja"), ("sold", "Vendido")],
        string="Estado nuevo",
    )
    weight = fields.Float(string="Peso registrado (kg)")
    health_event_type = fields.Selection(
        [
            ("vacuna", "Vacunación"),
            ("tratamiento", "Tratamiento"),
            ("revision", "Revisión veterinaria"),
            ("bienestar", "Bienestar / manejo"),
        ],
        string="Tipo sanitario",
    )
    health_description = fields.Char(string="Descripción sanitaria")
    health_veterinarian = fields.Char(string="Veterinario / responsable")
    retirement_reason = fields.Selection(
        [
            ("muerte", "Muerte"),
            ("enfermedad", "Enfermedad"),
            ("accidente", "Accidente"),
            ("venta", "Venta"),
            ("otro", "Otro"),
        ],
        string="Motivo de baja",
    )
    retirement_notes = fields.Text(string="Notas de baja")


class LivestockMovementWeightLine(models.Model):
    _name = "livestock.movement.weight.line"
    _description = "Detalle de peso por animal"

    movement_id = fields.Many2one("livestock.movement", string="Movimiento", required=True, ondelete="cascade")
    cattle_id = fields.Many2one(
        "livestock.cattle",
        string="Ganado",
        required=True,
        domain="[('state', '=', 'inventory')]",
    )
    weight = fields.Float(string="Peso (kg)", required=True)

    _sql_constraints = [
        (
            "livestock_movement_weight_line_unique",
            "unique(movement_id, cattle_id)",
            "No puede repetir el ganado en el mismo movimiento de pesos.",
        ),
    ]
