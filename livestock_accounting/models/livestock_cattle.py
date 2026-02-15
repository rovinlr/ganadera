from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class LivestockCattle(models.Model):
    _name = "livestock.cattle"
    _description = "Ficha de Ganado"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Nombre", required=True, tracking=True)
    sequence_code = fields.Char(string="Código", required=True, copy=False, readonly=True, default=lambda self: _("Nuevo"))
    ear_tag = fields.Char(string="Arete / Identificación", tracking=True)
    category_id = fields.Many2one("livestock.category", string="Categoría", required=True, tracking=True)
    breed_id = fields.Many2one("livestock.breed", string="Raza", required=True)
    inclusion_date = fields.Date(string="Fecha de nacimiento / inclusión", required=True, tracking=True)
    state = fields.Selection(
        [
            ("inventory", "En inventario"),
            ("retired", "Dado de baja"),
            ("sold", "Vendido"),
        ],
        default="inventory",
        string="Estado",
        required=True,
        tracking=True,
    )
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
    location_id = fields.Many2one("livestock.location", string="Ubicación / Lote")
    responsible_id = fields.Many2one("res.users", string="Responsable", default=lambda self: self.env.user)
    weight_line_ids = fields.One2many("livestock.weight.control", "cattle_id", string="Control de pesos")
    current_weight = fields.Float(string="Peso actual (kg)", compute="_compute_current_weight", store=True, tracking=True)
    cost_line_ids = fields.One2many("livestock.cost.history", "cattle_id", string="Coste histórico")
    total_historical_cost = fields.Monetary(string="Coste histórico acumulado", compute="_compute_total_historical_cost", store=True)
    current_cost_per_kg = fields.Monetary(string="Costo por kg", compute="_compute_current_cost_per_kg", store=False)
    currency_id = fields.Many2one("res.currency", string="Moneda", default=lambda self: self.env.company.currency_id, required=True)
    age_days = fields.Integer(string="Edad (días)", compute="_compute_age_days", store=False)
    age_years = fields.Float(string="Edad (años)", compute="_compute_age_years", store=False)
    health_event_ids = fields.One2many("livestock.health.event", "cattle_id", string="Sanidad y bienestar")
    movement_history_ids = fields.One2many("livestock.movement.history", "cattle_id", string="Histórico de movimientos", readonly=True)

    _sql_constraints = [
        ("livestock_cattle_sequence_unique", "unique(sequence_code)", "El código del ganado debe ser único."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("sequence_code", _("Nuevo")) == _("Nuevo"):
                vals["sequence_code"] = self.env["ir.sequence"].next_by_code("livestock.cattle") or _("Nuevo")
        return super().create(vals_list)

    @api.depends("weight_line_ids.weight", "weight_line_ids.date")
    def _compute_current_weight(self):
        for cattle in self:
            latest_line = cattle.weight_line_ids.sorted(key=lambda x: (x.date or fields.Date.today(), x.id), reverse=True)[:1]
            cattle.current_weight = latest_line.weight if latest_line else 0.0

    @api.depends("cost_line_ids.allocated_amount")
    def _compute_total_historical_cost(self):
        for cattle in self:
            cattle.total_historical_cost = sum(cattle.cost_line_ids.mapped("allocated_amount"))

    @api.depends("total_historical_cost", "current_weight")
    def _compute_current_cost_per_kg(self):
        for cattle in self:
            cattle.current_cost_per_kg = (
                cattle.total_historical_cost / cattle.current_weight if cattle.current_weight else 0.0
            )

    @api.depends("inclusion_date")
    def _compute_age_days(self):
        today = fields.Date.today()
        for cattle in self:
            cattle.age_days = (today - cattle.inclusion_date).days if cattle.inclusion_date else 0

    @api.depends("age_days")
    def _compute_age_years(self):
        for cattle in self:
            cattle.age_years = cattle.age_days / 365.0 if cattle.age_days else 0.0

    @api.constrains("retirement_reason", "state")
    def _check_retirement_reason(self):
        for cattle in self:
            if cattle.state in ("retired", "sold") and not cattle.retirement_reason:
                raise ValidationError(_("Debe indicar un motivo cuando el ganado está dado de baja o vendido."))
