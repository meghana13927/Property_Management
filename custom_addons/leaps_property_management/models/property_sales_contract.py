from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PropertySalesContract(models.Model):
    _name = 'property.sales.contract'
    _description = 'Property Sales Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_contract desc'
    _rec_name = 'name'

    name = fields.Char(string='Contract Reference', required=True, copy=False, default='New')
    unit_id = fields.Many2one(
        'property.unit', string='Property Unit', required=True, tracking=True,
        domain=[('state', 'in', ['available', 'booked'])],
    )
    buyer_id = fields.Many2one('res.partner', string='Buyer', required=True, tracking=True)
    seller_id = fields.Many2one(
        'res.partner', string='Seller / Owner',
        related='unit_id.owner_id', store=True,
    )

    # Contract Details
    date_contract = fields.Date(
        string='Contract Date', required=True, default=fields.Date.today,
    )
    date_completion = fields.Date(string='Expected Completion Date')

    # Financial
    sale_price = fields.Monetary(
        string='Sale Price', related='unit_id.sale_price', store=True,
    )
    agreed_price = fields.Monetary(string='Agreed Price', required=True, tracking=True)
    booking_amount = fields.Monetary(string='Booking Amount / EOI')
    down_payment = fields.Monetary(string='Down Payment')
    admin_fee = fields.Monetary(string='Admin Fee')
    stamp_duty = fields.Monetary(string='Stamp Duty')
    registration_fee = fields.Monetary(string='Registration Fee')
    currency_id = fields.Many2one(
        'res.currency', related='unit_id.currency_id', store=True,
    )

    # Payment Plan
    payment_plan_ids = fields.One2many(
        'property.payment.plan', 'sales_contract_id', string='Payment Plan',
    )
    total_paid = fields.Monetary(
        compute='_compute_totals', string='Total Paid', store=False,
    )
    balance_due = fields.Monetary(
        compute='_compute_totals', string='Balance Due', store=False,
    )

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('booked', 'Booked'),
        ('spa', 'SPA Signed'),
        ('completed', 'Completed / Transferred'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    invoice_ids = fields.One2many('account.move', 'sales_contract_id', string='Invoices')
    invoice_count = fields.Integer(compute='_compute_invoice_count', string='Invoices')
    commission_ids = fields.One2many('property.commission', 'sales_contract_id', string='Commissions')
    commission_count = fields.Integer(compute='_compute_commission_count', string='Commissions')
    notes = fields.Html(string='Terms & Notes')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('property.sales.contract') or 'New'
                )
        return super().create(vals_list)

    def _compute_totals(self):
        for rec in self:
            paid = sum(
                rec.payment_plan_ids.filtered(lambda p: p.state == 'paid').mapped('amount')
            )
            rec.total_paid = paid
            rec.balance_due = rec.agreed_price - paid

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids.filtered(lambda i: i.state != 'cancel'))

    @api.depends('commission_ids')
    def _compute_commission_count(self):
        for rec in self:
            rec.commission_count = len(rec.commission_ids)

    def action_view_commissions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Commissions',
            'res_model': 'property.commission',
            'view_mode': 'list,form',
            'domain': [('sales_contract_id', '=', self.id)],
            'context': {
                'default_sales_contract_id': self.id,
            },
        }

    def action_book(self):
        for rec in self:
            rec.state = 'booked'
            rec.unit_id.state = 'booked'
            self.env['property.commission'].create({
                'commission_type': 'leasing',
                'sales_contract_id': rec.id,
                'base_rent_amount': rec.agreed_price,
                'company_commission_rate': 2.5,
                'agent_share_rate': 25.0,
                'vat_applicable': True,
                'vat_rate': 15.0,
                'notes': f'Auto-created on booking of sales contract {rec.name}',
            })

    def action_sign_spa(self):
        self.state = 'spa'

    def action_complete(self):
        for rec in self:
            rec.state = 'completed'
            rec.unit_id.state = 'sold'
            # Auto-create full sale invoice on completion
            existing = self.env['account.move'].search([
                ('sales_contract_id', '=', rec.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if not existing:
                self.env['account.move'].create({
                    'move_type': 'out_invoice',
                    'partner_id': rec.buyer_id.id,
                    'invoice_date': rec.date_completion or fields.Date.today(),
                    'sales_contract_id': rec.id,
                    'invoice_line_ids': [(0, 0, {
                        'name': _('Sale of Property: %s') % rec.unit_id.name,
                        'quantity': 1,
                        'price_unit': rec.agreed_price,
                    })],
                })

    def action_cancel(self):
        self.state = 'cancelled'
        other_active = self.env['property.sales.contract'].search([
            ('unit_id', '=', self.unit_id.id),
            ('state', 'not in', ['cancelled', 'completed']),
            ('id', '!=', self.id),
        ])
        if not other_active:
            self.unit_id.state = 'available'

    def action_draft(self):
        self.state = 'draft'

    def action_view_invoices(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('sales_contract_id', '=', self.id)],
            'context': {
                'default_sales_contract_id': self.id,
                'default_move_type': 'out_invoice',
            },
        }


class PropertyPaymentPlan(models.Model):
    _name = 'property.payment.plan'
    _description = 'Payment Plan Installment'
    _order = 'due_date'

    sales_contract_id = fields.Many2one(
        'property.sales.contract', string='Sales Contract',
        required=True, ondelete='cascade',
    )
    name = fields.Char(string='Milestone', required=True)
    due_date = fields.Date(string='Due Date', required=True)
    amount = fields.Monetary(string='Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', related='sales_contract_id.currency_id',
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ], default='pending', string='Status')
    notes = fields.Char(string='Notes')
