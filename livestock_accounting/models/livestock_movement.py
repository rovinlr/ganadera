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

    weight = fields.Float(string="Peso (kg)")
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
    new_category = fields.Selection(
        [
            ("nacimiento", "Nacimientos"),
            ("desarrollo", "Desarrollo"),
            ("produccion", "Producción"),
        ],
        string="Nueva categoría",
    )

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

    @api.constrains("movement_type", "weight", "health_event_type", "health_description", "retirement_reason", "new_category")
    def _check_required_by_type(self):
        for movement in self:
            if movement.movement_type == "weight" and movement.weight <= 0:
                raise UserError(_("Debe indicar un peso mayor que cero para el registro masivo de peso."))
            if movement.movement_type == "health":
                if not movement.health_event_type or not movement.health_description:
                    raise UserError(_("Debe indicar tipo y descripción para el registro sanitario masivo."))
            if movement.movement_type == "retirement" and not movement.retirement_reason:
                raise UserError(_("Debe indicar el motivo para la baja masiva."))
            if movement.movement_type == "reclassification" and not movement.new_category:
                raise UserError(_("Debe indicar la nueva categoría para la reclasificación."))

    def action_apply(self):
        for movement in self:
            if movement.state == "applied":
                raise UserError(_("El movimiento %s ya fue aplicado.") % movement.name)
            if not movement.cattle_ids:
                raise UserError(_("Debe seleccionar al menos un animal."))
            movement._apply_to_cattle()
            movement.state = "applied"

    def _apply_to_cattle(self):
        self.ensure_one()
        history_values = []
        for cattle in self.cattle_ids:
            vals = {
                "movement_id": self.id,
                "cattle_id": cattle.id,
                "date": self.date,
                "movement_type": self.movement_type,
                "notes": self.notes,
                "from_category": cattle.category,
                "from_state": cattle.state,
            }

            if self.movement_type == "weight":
                self.env["livestock.weight.control"].create(
                    {
                        "cattle_id": cattle.id,
                        "date": self.date,
                        "weight": self.weight,
                        "notes": self.notes,
                    }
                )
                vals.update({"weight": self.weight})

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
                if cattle.category == self.new_category:
                    continue
                cattle.category = self.new_category
                vals.update({"to_category": self.new_category})

            vals.update({"to_category": cattle.category, "to_state": cattle.state})
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
    from_category = fields.Selection(
        [("nacimiento", "Nacimientos"), ("desarrollo", "Desarrollo"), ("produccion", "Producción")],
        string="Categoría anterior",
    )
    to_category = fields.Selection(
        [("nacimiento", "Nacimientos"), ("desarrollo", "Desarrollo"), ("produccion", "Producción")],
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
