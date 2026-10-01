from odoo import fields, models


class ResPartner(models.Model):
    """Extend res.partner with Saudi REGA / FAL license fields."""
    _inherit = 'res.partner'

    is_property_agent = fields.Boolean(
        string='Is Property Agent / Broker',
        help='Enable to mark this contact as a licensed real estate agent or broker.',
    )
    fal_license_no = fields.Char(
        string='FAL License No.',
        help='FAL license number issued by REGA (General Real Estate Authority) — '
             'required for all real estate brokerage and management in Saudi Arabia.',
    )
    fal_expiry_date = fields.Date(
        string='FAL License Expiry',
        help='Expiry date of the FAL license. Must be renewed through REGA.',
    )
    rega_registered = fields.Boolean(
        string='REGA Registered',
        help='Confirms this agent / company is registered with the General Real Estate Authority.',
    )
    vat_registered_ksa = fields.Boolean(
        string='VAT Registered (KSA)',
        help='If VAT-registered, a 15% VAT must be added to all commissions and management fees.',
    )
    vat_no_ksa = fields.Char(
        string='VAT Registration No. (KSA)',
    )
