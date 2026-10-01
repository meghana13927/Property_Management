from odoo import fields, models


class PropertyTenant(models.Model):
    _name = "property.tenant"
    _description = "Tenant"
    _order = "name"

    name = fields.Char(
        string="Tenant Name",
        required=True,
    )

    phone = fields.Char(
        string="Mobile Number",
    )

    email = fields.Char(
        string="Email",
    )

    permanent_address = fields.Text(
        string="Permanent Address",
    )

    property_id = fields.Many2one(
        "property.property",
        string="Property",
        required=True,
        ondelete="cascade",
        index=True,
    )

    house_number = fields.Char(
        string="House / Unit Number",
        required=True,
    )

    monthly_rent = fields.Float(
        string="Monthly Rent",
    )

    deposit_amount = fields.Float(
        string="Deposit Amount",
    )

    move_in_date = fields.Date(
        string="Move-in Date",
    )

    agreement_start_date = fields.Date(
        string="Agreement Start Date",
    )

    agreement_end_date = fields.Date(
        string="Agreement End Date",
    )

    status = fields.Selection(
        [
            ("active", "Occupied"),
            ("notice", "Notice Period"),
            ("vacated", "Vacated"),
        ],
        string="Occupancy Status",
        required=True,
        default="active",
    )

    notes = fields.Text(
        string="Notes",
    )