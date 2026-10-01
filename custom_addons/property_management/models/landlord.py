from odoo import fields, models


class PropertyLandlord(models.Model):
    _name = "property.landlord"
    _description = "Landlord"
    _order = "name"

    name = fields.Char(
        string="Landlord Name",
        required=True,
    )

    phone = fields.Char(
        string="Mobile Number",
    )

    email = fields.Char(
        string="Email",
    )

    address = fields.Text(
        string="Address",
    )

    property_ids = fields.One2many(
        "property.property",
        "landlord_id",
        string="Properties",
    )

    property_count = fields.Integer(
        string="Total Properties",
        compute="_compute_property_count",
    )

    notes = fields.Text(
        string="Notes",
    )

    def _compute_property_count(self):
        for record in self:
            record.property_count = len(record.property_ids)