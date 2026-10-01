from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PropertyMaintenance(models.Model):
    _name = 'property.maintenance'
    _description = 'Property Maintenance Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    # Identity
    name = fields.Char(
        string='Request Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New'),
    )
    unit_id = fields.Many2one(
        'property.unit', string='Property Unit',
        required=True, tracking=True, ondelete='restrict',
    )
    owner_id = fields.Many2one(
        'res.partner', string='Owner / Landlord',
        related='unit_id.owner_id', store=True, readonly=True,
    )
    tenant_id = fields.Many2one(
        'res.partner', string='Reported By (Tenant)',
        tracking=True,
    )

    # Dates
    request_date = fields.Date(
        string='Request Date', default=fields.Date.today, required=True, tracking=True,
    )
    scheduled_date = fields.Date(string='Scheduled Date', tracking=True)
    completion_date = fields.Date(string='Completion Date', tracking=True)

    # Type & Priority
    maintenance_type = fields.Selection([
        ('electrical', 'Electrical'),
        ('plumbing', 'Plumbing'),
        ('ac_hvac', 'AC / HVAC'),
        ('painting', 'Painting'),
        ('carpentry', 'Carpentry'),
        ('cleaning', 'Deep Cleaning'),
        ('appliances', 'Appliances'),
        ('structural', 'Structural'),
        ('pest_control', 'Pest Control'),
        ('security', 'Security / Locks'),
        ('other', 'Other'),
    ], string='Maintenance Type', required=True, default='other', tracking=True)

    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'High'),
        ('2', 'Very High / Urgent'),
    ], string='Priority', default='0', tracking=True)

    # State machine
    state = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='new', tracking=True, required=True)

    # Vendor / Contractor
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor / Contractor', tracking=True,
    )

    # Financials
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    estimated_cost = fields.Monetary(
        string='Estimated Cost', currency_field='currency_id',
    )
    actual_cost = fields.Monetary(
        string='Actual Cost', currency_field='currency_id',
    )

    # Description
    description = fields.Text(string='Problem Description')
    notes = fields.Html(string='Internal Notes')

    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
    )

    # ── Sequence ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'property.maintenance'
                ) or _('New')
        return super().create(vals_list)

    # ── State transitions ──────────────────────────────────────────────────────
    def action_assign(self):
        for rec in self:
            if not rec.vendor_id:
                raise ValidationError(_('Please assign a Vendor / Contractor before marking as Assigned.'))
            rec.state = 'assigned'

    def action_start(self):
        for rec in self:
            rec.state = 'in_progress'
            # Set unit to Under Maintenance if it's available or rented
            if rec.unit_id.state in ('available', 'rented', 'booked'):
                rec.unit_id.state = 'maintenance'

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            rec.completion_date = fields.Date.today()
            # Restore unit to available if it was under maintenance
            if rec.unit_id.state == 'maintenance':
                # Check if other open maintenance requests exist
                others = self.search([
                    ('unit_id', '=', rec.unit_id.id),
                    ('state', 'in', ('new', 'assigned', 'in_progress')),
                    ('id', '!=', rec.id),
                ])
                if not others:
                    rec.unit_id.state = 'available'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_reset(self):
        for rec in self:
            rec.state = 'new'
            rec.completion_date = False

