from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LivestockWeightControl(models.Model):
    _name = "livestock.weight.control"
    _description = "Control de pesos por fecha"
    _order = "date desc, id desc"

    cattle_id = fields.Many2one("livestock.cattle", string="Ganado", required=True, ondelete="cascade")
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    weight = fields.Float(string="Peso (kg)", required=True)
    notes = fields.Char(string="Notas")

    @api.constrains("weight")
    def _check_weight_positive(self):
        for line in self:
            if line.weight <= 0:
                raise ValidationError("El peso debe ser mayor que cero.")
