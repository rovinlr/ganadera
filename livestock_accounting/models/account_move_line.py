from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    livestock_category = fields.Selection(
        [
            ("nacimiento", "Nacimientos"),
            ("desarrollo", "Desarrollo"),
            ("produccion", "Producción"),
        ],
        string="Categoría ganadera",
        help="Categoría del hato a la que corresponde el coste de esta línea de factura.",
    )
    livestock_allocation_line_ids = fields.One2many("livestock.cost.history", "move_line_id", string="Asignaciones ganaderas")
