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
    invoice_line_ids = fields.Many2many(
        "account.move.line",
        "livestock_alloc_line_rel",
        "allocation_id",
        "move_line_id",
        string="Líneas de factura de proveedor",
        domain="[('move_id.move_type', '=', 'in_invoice'), ('move_id.state', '=', 'posted')]",
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
        return super().create(vals_list)

    @api.depends("invoice_line_ids.price_subtotal")
    def _compute_total_to_allocate(self):
        for allocation in self:
            allocation.total_to_allocate = sum(allocation.invoice_line_ids.mapped("price_subtotal"))

    def action_allocate_costs(self):
        self.ensure_one()
        if not self.cattle_ids:
            raise UserError(_("Debe seleccionar ganado para asignar costes."))
        if not self.invoice_line_ids:
            raise UserError(_("Debe seleccionar al menos una línea de factura."))
        if self.state == "done":
            raise UserError(_("Esta asignación ya fue procesada."))

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
