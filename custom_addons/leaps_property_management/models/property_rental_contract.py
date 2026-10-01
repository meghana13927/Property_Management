from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta


class PropertyRentalContract(models.Model):
    _name = 'property.rental.contract'
    _description = 'Property Rental Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'
    _rec_name = 'name'

    name = fields.Char(string='Contract Reference', required=True, copy=False, default='New')
    unit_id = fields.Many2one(
        'property.unit', string='Property Unit', required=True, tracking=True,
        domain=[('state', 'in', ['available', 'booked'])],
    )
    tenant_id = fields.Many2one('res.partner', string='Tenant', required=True, tracking=True)
    owner_id = fields.Many2one(
        'res.partner', string='Landlord / Owner',
        related='unit_id.owner_id', store=True,
    )

    # Contract Period
    date_start = fields.Date(string='Start Date', required=True, tracking=True)
    date_end = fields.Date(string='End Date', required=True, tracking=True)
    payment_term = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly (3 months)'),
        ('biannual', 'Bi-Annual (6 months)'),
        ('yearly', 'Yearly'),
    ], string='Payment Terms', default='monthly', required=True)

    # Financial
    rent_amount = fields.Monetary(
        string='Rent Amount', related='unit_id.rent_amount', store=True,
    )
    security_deposit = fields.Monetary(string='Security Deposit', tracking=True)
    admin_fee = fields.Monetary(string='Administrative Fee')
    currency_id = fields.Many2one(
        'res.currency', related='unit_id.currency_id', store=True,
    )

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
        ('renewed', 'Renewed'),
    ], string='Status', default='draft', tracking=True)

    # Invoice tracking
    invoice_ids = fields.One2many('account.move', 'rental_contract_id', string='Invoices')
    invoice_count = fields.Integer(compute='_compute_invoice_count', string='Invoice Count')
    total_invoiced = fields.Monetary(compute='_compute_invoice_count', string='Total Invoiced')

    # ── Saudi Arabia / REGA ────────────────────────────────────────────────────
    is_renewal = fields.Boolean(
        string='Contract Renewal',
        help='Check if this is a renewal. Per REGA/Ejar: the 2.5% commission '
             'cannot be charged again on renewals.',
    )
    ejar_registration_no = fields.Char(
        string='Ejar Registration No.',
        help='Residential leases must be registered on the Ejar platform to be legally binding.',
    )
    ejar_fee = fields.Monetary(
        string='Ejar Platform Fee',
        default=125.0,
        currency_field='currency_id',
        help='125 SAR for residential contracts (paid by landlord per Ejar regulations).',
    )
    renewal_admin_fee = fields.Monetary(
        string='Renewal Admin Fee',
        currency_field='currency_id',
        help='Flat admin fee for renewals: typically 200–500 SAR. '
             'Replaces the 2.5% leasing commission on renewals.',
    )
    # Leasing Commission
    leasing_commission_rate = fields.Float(
        string='Leasing Commission (%)',
        default=2.5,
        help='REGA standard: 2.5% of the first year\'s total rent.',
    )
    leasing_commission_amount = fields.Monetary(
        string='Leasing Commission',
        compute='_compute_rega_fees', store=True,
        currency_field='currency_id',
    )
    tenant_pays_commission = fields.Boolean(
        string='Tenant Pays Commission',
        default=True,
        help='REGA standard: leasing commission is traditionally paid by the Tenant.',
    )
    # Property Management Fee
    management_fee_type = fields.Selection([
        ('residential', 'Residential (5%–8%)'),
        ('commercial',  'Commercial (7%–12%)'),
    ], string='Asset Class', default='residential')
    management_fee_rate = fields.Float(
        string='Management Fee (%)',
        default=6.5,
        help='Residential: 5–8% | Commercial: 7–12% of total annual collected rent.',
    )
    management_fee_amount = fields.Monetary(
        string='Management Fee (Annual)',
        compute='_compute_rega_fees', store=True,
        currency_field='currency_id',
    )
    # VAT (15% KSA)
    vat_applicable = fields.Boolean(
        string='VAT Applicable (15%)',
        help='Add 15% VAT to commissions and fees if VAT-registered in Saudi Arabia.',
    )
    vat_amount = fields.Monetary(
        string='VAT on Commission (15%)',
        compute='_compute_rega_fees', store=True,
        currency_field='currency_id',
    )
    # Commission records
    commission_ids = fields.One2many(
        'property.commission', 'rental_contract_id', string='Commission Records',
    )
    commission_count = fields.Integer(
        compute='_compute_commission_count', string='Commissions',
    )

    notes = fields.Html(string='Terms & Notes')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('property.rental.contract') or 'New'
                )
        return super().create(vals_list)

    def _compute_invoice_count(self):
        for rec in self:
            invoices = rec.invoice_ids.filtered(lambda i: i.state != 'cancel')
            rec.invoice_count = len(invoices)
            rec.total_invoiced = sum(invoices.mapped('amount_total'))

    @api.depends('rent_amount', 'leasing_commission_rate', 'management_fee_rate',
                 'total_invoiced', 'vat_applicable')
    def _compute_rega_fees(self):
        for rec in self:
            annual_rent = (rec.rent_amount or 0.0) * 12.0
            lc = annual_rent * rec.leasing_commission_rate / 100.0
            mf = (rec.total_invoiced or 0.0) * rec.management_fee_rate / 100.0
            vat = (lc * 0.15) if rec.vat_applicable else 0.0
            rec.leasing_commission_amount = lc
            rec.management_fee_amount = mf
            rec.vat_amount = vat

    def _compute_commission_count(self):
        for rec in self:
            rec.commission_count = len(rec.commission_ids)

    def action_create_leasing_commission(self):
        """Create a leasing commission record from the contract."""
        self.ensure_one()
        annual_rent = (self.rent_amount or 0.0) * 12.0
        commission = self.env['property.commission'].create({
            'commission_type': 'leasing',
            'rental_contract_id': self.id,
            'base_rent_amount': annual_rent,
            'company_commission_rate': self.leasing_commission_rate,
            'vat_applicable': self.vat_applicable,
            'payer': 'tenant' if self.tenant_pays_commission else 'landlord',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leasing Commission',
            'res_model': 'property.commission',
            'view_mode': 'form',
            'res_id': commission.id,
        }

    def action_view_commissions(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Commissions',
            'res_model': 'property.commission',
            'view_mode': 'list,form',
            'domain': [('rental_contract_id', '=', self.id)],
            'context': {'default_rental_contract_id': self.id},
        }

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end <= rec.date_start:
                raise ValidationError(_('End date must be after start date.'))

    def action_activate(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft contracts can be activated.'))
            rec.unit_id.state = 'rented'
            rec.state = 'active'
            # Auto-generate rent invoices based on payment term and contract dates
            rec._generate_rent_invoices()

    def action_terminate(self):
        for rec in self:
            rec.state = 'terminated'
            other = self.search([
                ('unit_id', '=', rec.unit_id.id),
                ('state', '=', 'active'),
                ('id', '!=', rec.id),
            ])
            if not other:
                rec.unit_id.state = 'available'

    def action_expire(self):
        for rec in self:
            rec.state = 'expired'
            other = self.search([
                ('unit_id', '=', rec.unit_id.id),
                ('state', '=', 'active'),
                ('id', '!=', rec.id),
            ])
            if not other:
                rec.unit_id.state = 'available'

    def action_draft(self):
        self.state = 'draft'

    def _generate_rent_invoices(self):
        """Create rent invoices for the full contract period based on payment_term."""
        AccountMove = self.env['account.move']
        interval_map = {'monthly': 1, 'quarterly': 3, 'biannual': 6, 'yearly': 12}
        months = interval_map.get(self.payment_term, 1)
        term_label = dict(self._fields['payment_term'].selection).get(self.payment_term, '')

        current = self.date_start
        created = 0
        while current < self.date_end:
            period_end = current + relativedelta(months=months) - relativedelta(days=1)
            if period_end > self.date_end:
                period_end = self.date_end

            existing = AccountMove.search([
                ('rental_contract_id', '=', self.id),
                ('invoice_date', '=', current),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if not existing:
                AccountMove.create({
                    'move_type': 'out_invoice',
                    'partner_id': self.tenant_id.id,
                    'invoice_date': current,
                    'rental_contract_id': self.id,
                    'narration': _('Contract: %s | %s') % (self.name, term_label),
                    'invoice_line_ids': [(0, 0, {
                        'name': _('Rent: %s (%s to %s)') % (
                            self.unit_id.name,
                            current.strftime('%d/%m/%Y'),
                            period_end.strftime('%d/%m/%Y'),
                        ),
                        'quantity': 1,
                        'price_unit': self.rent_amount,
                    })],
                })
                created += 1
            current = current + relativedelta(months=months)
        return created

    def action_generate_invoices(self):
        """Manually regenerate rent invoices (skips already-created periods)."""
        self.ensure_one()
        if self.state not in ('active', 'expired', 'renewed'):
            raise UserError(_('Contract must be active to generate invoices.'))
        created = self._generate_rent_invoices()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Invoices Generated'),
                'message': _('%s new invoice(s) created.') % created,
                'type': 'success',
            },
        }

    def action_view_invoices(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('rental_contract_id', '=', self.id)],
            'context': {
                'default_rental_contract_id': self.id,
                'default_move_type': 'out_invoice',
            },
        }
