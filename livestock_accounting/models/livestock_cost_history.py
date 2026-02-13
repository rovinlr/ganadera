from odoo import fields, models


class LivestockCostHistory(models.Model):
    _name = "livestock.cost.history"
    _description = "Coste histórico de ganado"
    _order = "allocation_date desc, id desc"

    cattle_id = fields.Many2one("livestock.cattle", string="Ganado", required=True, ondelete="cascade")
    move_line_id = fields.Many2one(
        "account.move.line",
        string="Línea de factura",
        required=True,
        domain="[('move_id.move_type', '=', 'in_invoice')]",
        ondelete="restrict",
    )
    allocation_id = fields.Many2one("livestock.cost.allocation", string="Asignación", ondelete="set null")
    allocation_date = fields.Date(string="Fecha de asignación", required=True, default=fields.Date.context_today)
    source_document = fields.Char(string="Documento origen", related="move_line_id.move_name", store=True)
    allocated_amount = fields.Monetary(string="Coste asignado", required=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        related="move_line_id.currency_id",
        store=True,
        readonly=True,
    )
    method = fields.Selection(
        [("equal", "Igualitario"), ("weight", "Por peso"), ("age", "Por edad")],
        string="Método de asignación",
        required=True,
    )
    note = fields.Char(string="Nota")
