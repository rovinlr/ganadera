from odoo import fields, models


class LivestockCategory(models.Model):
    _name = "livestock.category"
    _description = "Categoría ganadera"
    _order = "name"

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("livestock_category_name_unique", "unique(name)", "La categoría ya existe."),
    ]


class LivestockBreed(models.Model):
    _name = "livestock.breed"
    _description = "Raza ganadera"
    _order = "name"

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("livestock_breed_name_unique", "unique(name)", "La raza ya existe."),
    ]


class LivestockLocation(models.Model):
    _name = "livestock.location"
    _description = "Ubicación o lote"
    _order = "name"

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("livestock_location_name_unique", "unique(name)", "La ubicación o lote ya existe."),
    ]
