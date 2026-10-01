from odoo import api, fields, models


class PropertyProperty(models.Model):
    _name = "property.property"
    _description = "Property"
    _order = "name"

    name = fields.Char(
        string="Property Name",
        required=True,
    )

    landlord_id = fields.Many2one(
        "property.landlord",
        string="Landlord",
        ondelete="set null",
    )

    # Compatibility field for older property views.
    # Data comes from the real landlord relationship.
    owner_name = fields.Char(
        string="Owner Name",
        related="landlord_id.name",
        readonly=True,
    )

    property_type = fields.Selection(
        [
            ("apartment", "Apartment"),
            ("house", "House"),
            ("villa", "Villa"),
            ("commercial", "Commercial"),
            ("office", "Office"),
            ("land", "Land"),
        ],
        string="Property Type",
        required=True,
        default="apartment",
    )

    address = fields.Text(
        string="Address",
    )

    status = fields.Selection(
        [
            ("available", "Available"),
            ("occupied", "Occupied"),
            ("maintenance", "Under Maintenance"),
        ],
        string="Status",
        required=True,
        default="available",
    )

    tenant_ids = fields.One2many(
        "property.tenant",
        "property_id",
        string="Tenants",
    )

    tenant_count = fields.Integer(
        string="Total Tenants",
        compute="_compute_tenant_statistics",
    )

    active_tenant_count = fields.Integer(
        string="Occupied",
        compute="_compute_tenant_statistics",
    )

    total_monthly_rent = fields.Float(
        string="Total Monthly Rent",
        compute="_compute_tenant_statistics",
    )

    # Compatibility field for old views.
    # It shows all active tenant names.
    tenant_name = fields.Char(
        string="Tenant Name",
        compute="_compute_tenant_name",
    )

    notes = fields.Text(
        string="Notes",
    )

    @api.depends(
        "tenant_ids",
        "tenant_ids.status",
        "tenant_ids.monthly_rent",
    )
    def _compute_tenant_statistics(self):
        for record in self:
            record.tenant_count = len(record.tenant_ids)

            active_tenants = record.tenant_ids.filtered(
                lambda tenant: tenant.status == "active"
            )

            record.active_tenant_count = len(active_tenants)

            record.total_monthly_rent = sum(
                active_tenants.mapped("monthly_rent")
            )

    @api.depends(
        "tenant_ids",
        "tenant_ids.name",
        "tenant_ids.status",
    )
    def _compute_tenant_name(self):
        for record in self:
            active_tenants = record.tenant_ids.filtered(
                lambda tenant: tenant.status == "active"
            )

            record.tenant_name = ", ".join(
                active_tenants.mapped("name")
            )