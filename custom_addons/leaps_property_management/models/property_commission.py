from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PropertyCommission(models.Model):
    _name = 'property.commission'
    _description = 'REGA Commission & Fee'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Commission Reference', required=True, copy=False,
        readonly=True, default=lambda self: _('New'),
    )
    commission_type = fields.Selection([
        ('leasing',          'Leasing Commission (2.5%)'),
        ('management',       'Property Management Fee'),
        ('renewal',          'Contract Renewal Fee'),
        ('collection_bonus', 'Collection / Recovery Bonus'),
        ('kpi',              'KPI / Occupancy Bonus'),
    ], string='Commission Type', required=True, default='leasing', tracking=True)

    # Links
    rental_contract_id = fields.Many2one(
        'property.rental.contract', string='Rental Contract',
        ondelete='cascade', tracking=True,
    )
    sales_contract_id = fields.Many2one(
        'property.sales.contract', string='Sales Contract',
        ondelete='set null', index=True, tracking=True,
    )
    unit_id = fields.Many2one(
        'property.unit', string='Property Unit',
        related='rental_contract_id.unit_id', store=True, readonly=True,
    )

    # Agent
    agent_id = fields.Many2one(
        'res.partner', string='Agent / Broker',
        domain=[('is_property_agent', '=', True)],
        tracking=True,
    )
    fal_license_no = fields.Char(
        string='FAL License No.',
        related='agent_id.fal_license_no', store=True, readonly=True,
    )
    fal_expiry_date = fields.Date(
        string='FAL Expiry',
        related='agent_id.fal_expiry_date', store=True, readonly=True,
    )

    # Dates & Period
    date = fields.Date(
        string='Commission Date', default=fields.Date.today, required=True,
    )
    ejar_registration_no = fields.Char(
        string='Ejar Registration No.',
        help='Ejar registration number for the lease — required for residential contracts.',
    )

    # Gross commission (what the company earns)
    base_rent_amount = fields.Monetary(
        string='Annual Rent (Base)',
        help='Annual rent used to calculate the leasing commission.',
        currency_field='currency_id',
    )
    company_commission_rate = fields.Float(
        string='Company Rate (%)',
        default=2.5,
        help='REGA standard: 2.5% of first-year rent for leasing commission.',
    )
    company_commission_amount = fields.Monetary(
        string='Company Commission',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
        help='Gross commission earned by the company.',
    )

    # Agent share
    agent_share_rate = fields.Float(
        string='Agent Share (%)',
        default=25.0,
        help='Standard: 25%-30% of company commission for leasing agents.',
    )
    agent_amount = fields.Monetary(
        string='Agent Commission',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
    )

    # VAT
    vat_applicable = fields.Boolean(
        string='VAT Applicable (15%)', default=True,
        help='Saudi Arabia: 15% VAT applies if the company/individual is VAT-registered.',
    )
    vat_rate = fields.Float(string='VAT Rate (%)', default=15.0)
    vat_amount = fields.Monetary(
        string='VAT Amount',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
    )
    total_with_vat = fields.Monetary(
        string='Total (incl. VAT)',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
    )

    # Currency
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    # Vendor Bill
    vendor_bill_id = fields.Many2one(
        'account.move', string='Agent Bill', ondelete='set null', copy=False, readonly=True,
        domain=[('move_type', '=', 'in_invoice')],
    )
    vendor_bill_count = fields.Integer(compute='_compute_vendor_bill_count')

    # State
    state = fields.Selection([
        ('draft',    'Draft'),
        ('approved', 'Approved'),
        ('invoiced', 'Invoiced'),
        ('paid',     'Paid'),
    ], string='Status', default='draft', tracking=True)

    # Payer
    payer = fields.Selection([
        ('tenant',   'Tenant (Standard)'),
        ('landlord', 'Landlord'),
        ('split',    'Split 50/50'),
    ], string='Commission Payer', default='tenant',
       help='Per REGA: leasing commission is typically paid by the Tenant.')

    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    # ── Sequence ───────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('property.commission') or _('New')
                )
        return super().create(vals_list)

    # ── Compute ────────────────────────────────────────────────────────────────
    @api.depends('vendor_bill_id')
    def _compute_vendor_bill_count(self):
        for rec in self:
            rec.vendor_bill_count = 1 if rec.vendor_bill_id else 0

    @api.depends('base_rent_amount', 'company_commission_rate',
                 'agent_share_rate', 'vat_applicable', 'vat_rate')
    def _compute_amounts(self):
        for rec in self:
            co = rec.base_rent_amount * rec.company_commission_rate / 100.0
            ag = co * rec.agent_share_rate / 100.0
            vat = ag * rec.vat_rate / 100.0 if rec.vat_applicable else 0.0
            rec.company_commission_amount = co
            rec.agent_amount = ag
            rec.vat_amount = vat
            rec.total_with_vat = ag + vat

    # ── FAL validation ─────────────────────────────────────────────────────────
    @api.constrains('agent_id', 'commission_type')
    def _check_fal_license(self):
        for rec in self:
            if rec.agent_id and not rec.agent_id.fal_license_no:
                raise ValidationError(_(
                    'Agent "%s" does not have a FAL License number. '
                    'Per REGA regulations, every broker must hold a valid FAL License.'
                ) % rec.agent_id.name)

    # ── State transitions ──────────────────────────────────────────────────────
    def action_approve(self):
        self.state = 'approved'

    def action_invoice(self):
        self.ensure_one()
        if not self.agent_id:
            raise UserError(_('Please set an Agent / Broker before creating a bill.'))
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.agent_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': f'Commission: {self.name}',
                'quantity': 1,
                'price_unit': self.total_with_vat or self.agent_amount,
            })],
        })
        self.vendor_bill_id = bill
        self.state = 'invoiced'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
        }

    def action_view_vendor_bill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agent Bill',
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
        }

    def action_paid(self):
        self.state = 'paid'

    def action_reset(self):
        self.state = 'draft'
