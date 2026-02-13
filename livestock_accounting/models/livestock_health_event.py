from odoo import fields, models


class LivestockHealthEvent(models.Model):
    _name = "livestock.health.event"
    _description = "Registro sanitario y bienestar"
    _order = "date desc, id desc"

    cattle_id = fields.Many2one("livestock.cattle", string="Ganado", required=True, ondelete="cascade")
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    event_type = fields.Selection(
        [
            ("vacuna", "Vacunación"),
            ("tratamiento", "Tratamiento"),
            ("revision", "Revisión veterinaria"),
            ("bienestar", "Bienestar / manejo"),
        ],
        string="Tipo",
        required=True,
    )
    description = fields.Char(string="Descripción", required=True)
    veterinarian = fields.Char(string="Veterinario / responsable")
    notes = fields.Text(string="Notas")
