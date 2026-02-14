from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LivestockCostAllocation(models.Model):
    _name = "livestock.cost.allocation"
    _description = "Asignación de costes al ganado"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Referencia", default=lambda self: _("Nuevo"), readonly=True, copy=False)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    cattle_ids = fields.Many2many("livestock.cattle", string="Ganado a costear", domain="[('state','=','inventory')]")
    allocation_line_ids = fields.One2many("livestock.cost.allocation.line", "allocation_id", string="Líneas disponibles")
    invoice_line_ids = fields.Many2many(
        "account.move.line",
        compute="_compute_invoice_line_ids",
        string="Líneas de factura seleccionadas",
        store=False,
    )
    method = fields.Selection(
        [("equal", "Igual para todos"), ("weight", "Por peso"), ("age", "Por edad")],
        string="Método de asignación",
        required=True,
        default="equal",
    )
    total_to_allocate = fields.Monetary(string="Total a asignar", compute="_compute_total_to_allocate", store=False)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id, required=True)
    note = fields.Text(string="Observaciones")
    state = fields.Selection([("draft", "Borrador"), ("done", "Asignado")], default="draft", tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo")) == _("Nuevo"):
                vals["name"] = self.env["ir.sequence"].next_by_code("livestock.cost.allocation") or _("Nuevo")
        allocations = super().create(vals_list)
        allocations._sync_available_invoice_lines()
        return allocations

    def write(self, vals):
        result = super().write(vals)
        if {"company_id", "state"}.intersection(vals.keys()):
            self.filtered(lambda r: r.state == "draft")._sync_available_invoice_lines()
        return result

    @api.depends("allocation_line_ids.selected", "allocation_line_ids.move_line_id")
    def _compute_invoice_line_ids(self):
        for allocation in self:
            selected_lines = allocation.allocation_line_ids.filtered("selected").mapped("move_line_id")
            allocation.invoice_line_ids = selected_lines

    @api.depends("allocation_line_ids.selected", "allocation_line_ids.move_line_id.price_subtotal")
    def _compute_total_to_allocate(self):
        for allocation in self:
            selected_lines = allocation.allocation_line_ids.filtered("selected").mapped("move_line_id")
            allocation.total_to_allocate = sum(selected_lines.mapped("price_subtotal"))

    def _get_allocated_move_line_ids(self):
        return self.env["livestock.cost.history"].search([("move_line_id", "!=", False)]).mapped("move_line_id").ids

    def _get_reserved_move_line_ids(self):
        self.ensure_one()
        domain = [
            ("allocation_id.state", "=", "draft"),
            ("selected", "=", True),
            ("move_line_id", "!=", False),
        ]
        if self.id:
            domain.append(("allocation_id", "!=", self.id))
        return self.env["livestock.cost.allocation.line"].search(domain).mapped("move_line_id").ids

    def _get_available_invoice_lines(self):
        self.ensure_one()
        unavailable_line_ids = set(self._get_allocated_move_line_ids())
        unavailable_line_ids.update(self._get_reserved_move_line_ids())
        domain = [
            ("move_id.move_type", "=", "in_invoice"),
            ("move_id.state", "=", "posted"),
            ("display_type", "in", [False, "product"]),
            ("company_id", "=", self.company_id.id),
        ]
        if "exclude_from_invoice_tab" in self.env["account.move.line"]._fields:
            domain.append(("exclude_from_invoice_tab", "=", False))
        if unavailable_line_ids:
            domain.append(("id", "not in", list(unavailable_line_ids)))
        return self.env["account.move.line"].search(domain)

    def _sync_available_invoice_lines(self):
        for allocation in self:
            if allocation.state == "done":
                continue
            selected_by_move_line = {
                line.move_line_id.id: line.selected
                for line in allocation.allocation_line_ids
                if line.move_line_id
            }
            commands = [fields.Command.clear()]
            for move_line in allocation._get_available_invoice_lines():
                commands.append(
                    fields.Command.create(
                        {
                            "move_line_id": move_line.id,
                            "selected": selected_by_move_line.get(move_line.id, False),
                        }
                    )
                )
            allocation.allocation_line_ids = commands

    def action_refresh_available_lines(self):
        self._sync_available_invoice_lines()

    def action_open_line_selection_wizard(self):
        self.ensure_one()
        self._sync_available_invoice_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Seleccionar facturas"),
            "res_model": "livestock.cost.allocation.select.lines.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_allocation_id": self.id},
        }

    def action_allocate_costs(self):
        self.ensure_one()
        if not self.cattle_ids:
            raise UserError(_("Debe seleccionar ganado para asignar costes."))
        if not self.invoice_line_ids:
            raise UserError(_("Debe seleccionar al menos una línea de factura."))
        if self.state == "done":
            raise UserError(_("Esta asignación ya fue procesada."))

        allocated_lines = self.env["livestock.cost.history"].search([
            ("move_line_id", "in", self.invoice_line_ids.ids)
        ]).mapped("move_line_id")
        if allocated_lines:
            raise UserError(
                _("Las siguientes líneas ya fueron asignadas en otro proceso: %s")
                % ", ".join(allocated_lines.mapped("display_name"))
            )

        total = self.total_to_allocate
        if total <= 0:
            raise UserError(_("El total a asignar debe ser mayor que cero."))

        factors = self._get_allocation_factors()
        factor_sum = sum(factors.values())
        if factor_sum <= 0:
            raise UserError(_("No se pudo calcular una base válida para el método de asignación."))

        for line in self.invoice_line_ids:
            eligible_cattle = self.cattle_ids.filtered(lambda c: not line.livestock_category or c.category == line.livestock_category)
            if not eligible_cattle:
                continue
            eligible_sum = sum(factors[c.id] for c in eligible_cattle)
            for cattle in eligible_cattle:
                amount = line.price_subtotal * (factors[cattle.id] / eligible_sum)
                self.env["livestock.cost.history"].create(
                    {
                        "cattle_id": cattle.id,
                        "move_line_id": line.id,
                        "allocation_id": self.id,
                        "allocation_date": self.date,
                        "allocated_amount": amount,
                        "method": self.method,
                        "note": _("Asignación %s") % self.name,
                    }
                )

        self.state = "done"

    def _get_allocation_factors(self):
        self.ensure_one()
        factors = {}
        for cattle in self.cattle_ids:
            if self.method == "equal":
                factors[cattle.id] = 1.0
            elif self.method == "weight":
                factors[cattle.id] = cattle.current_weight or 0.0
            else:
                factors[cattle.id] = max(cattle.age_days, 1)
        return factors


class LivestockCostAllocationLine(models.Model):
    _name = "livestock.cost.allocation.line"
    _description = "Línea disponible para asignación de costes"
    _order = "selected desc, id desc"

    allocation_id = fields.Many2one("livestock.cost.allocation", required=True, ondelete="cascade")
    selected = fields.Boolean(string="Seleccionar")
    move_line_id = fields.Many2one("account.move.line", string="Línea de factura", required=True, ondelete="cascade")
    move_id = fields.Many2one(related="move_line_id.move_id", string="Factura", store=False, readonly=True)
    partner_id = fields.Many2one(related="move_line_id.partner_id", string="Proveedor", store=False, readonly=True)
    date = fields.Date(related="move_line_id.date", string="Fecha", store=False, readonly=True)
    price_subtotal = fields.Monetary(related="move_line_id.price_subtotal", string="Subtotal", store=False, readonly=True)
    livestock_category = fields.Selection(related="move_line_id.livestock_category", string="Categoría", store=False, readonly=True)
    currency_id = fields.Many2one(related="move_line_id.currency_id", store=False, readonly=True)


class LivestockCostAllocationSelectLinesWizard(models.TransientModel):
    _name = "livestock.cost.allocation.select.lines.wizard"
    _description = "Asistente para seleccionar facturas"

    allocation_id = fields.Many2one("livestock.cost.allocation", required=True, readonly=True)
    available_line_ids = fields.Many2many(
        "account.move.line",
        "lca_sel_wiz_avail_rel",
        "wizard_id",
        "move_line_id",
        string="Líneas disponibles",
        readonly=True,
    )
    selected_line_ids = fields.Many2many(
        "account.move.line",
        "lca_sel_wiz_selected_rel",
        "wizard_id",
        "move_line_id",
        string="Líneas de factura a cargar",
        domain="[('id', 'in', available_line_ids)]",
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        allocation = self.env["livestock.cost.allocation"].browse(defaults.get("allocation_id"))
        if not allocation:
            return defaults
        available_lines = allocation._get_available_invoice_lines()
        selected_lines = allocation.allocation_line_ids.filtered("selected").mapped("move_line_id") & available_lines
        defaults.update(
            {
                "available_line_ids": [fields.Command.set(available_lines.ids)],
                "selected_line_ids": [fields.Command.set(selected_lines.ids)],
            }
        )
        return defaults

    def action_apply_selection(self):
        self.ensure_one()
        self.allocation_id._sync_available_invoice_lines()
        selected_ids = set(self.selected_line_ids.ids)
        for line in self.allocation_id.allocation_line_ids:
            line.selected = line.move_line_id.id in selected_ids
        return {"type": "ir.actions.act_window_close"}
