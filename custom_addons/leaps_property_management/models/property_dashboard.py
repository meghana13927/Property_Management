from odoo import api, fields, models
from datetime import date


class PropertyDashboard(models.TransientModel):
    _name = 'property.dashboard'
    _description = 'Property Management Dashboard'
    _rec_name = 'name'

    name = fields.Char(default='لوحة تحكم إدارة العقارات', readonly=True)

    # Unit KPIs
    total_units       = fields.Integer(string='Total Units', readonly=True)
    available_units   = fields.Integer(string='Available', readonly=True)
    rented_units      = fields.Integer(string='Rented', readonly=True)
    sold_units        = fields.Integer(string='Sold', readonly=True)
    booked_units      = fields.Integer(string='Booked', readonly=True)
    maintenance_units = fields.Integer(string='Under Maintenance', readonly=True)
    occupancy_rate    = fields.Float(string='Occupancy Rate (%)', readonly=True, digits=(5, 1))

    # Contract KPIs
    active_contracts  = fields.Integer(string='Active Rental Contracts', readonly=True)
    expiring_30d      = fields.Integer(string='Expiring in 30 Days', readonly=True)
    active_sales      = fields.Integer(string='Active Sales Contracts', readonly=True)

    # Financial KPIs
    currency_id       = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    revenue_ytd       = fields.Monetary(string='Revenue YTD', readonly=True, currency_field='currency_id')
    revenue_mtd       = fields.Monetary(string='Revenue MTD', readonly=True, currency_field='currency_id')
    pending_invoices  = fields.Monetary(string='Pending Invoices', readonly=True, currency_field='currency_id')
    overdue_invoices  = fields.Monetary(string='Overdue Invoices', readonly=True, currency_field='currency_id')

    # Maintenance KPIs
    open_maintenance   = fields.Integer(string='Open Maintenance', readonly=True)
    urgent_maintenance = fields.Integer(string='Urgent Maintenance', readonly=True)
    maint_cost_ytd     = fields.Monetary(string='Maintenance Cost YTD', readonly=True, currency_field='currency_id')

    # Commission KPIs
    pending_commissions  = fields.Monetary(string='Pending Commissions', readonly=True, currency_field='currency_id')
    paid_commissions_ytd = fields.Monetary(string='Commissions Paid YTD', readonly=True, currency_field='currency_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = date.today()
        year_start = today.replace(month=1, day=1)
        month_start = today.replace(day=1)
        from datetime import timedelta
        in_30d = today + timedelta(days=30)

        Unit = self.env['property.unit']
        RentalContract = self.env['property.rental.contract']
        SalesContract = self.env['property.sales.contract']
        Maintenance = self.env['property.maintenance']
        Commission = self.env['property.commission']
        Invoice = self.env['account.move']

        units = Unit.search([])
        res.update({
            'total_units':       len(units),
            'available_units':   len(units.filtered(lambda u: u.state == 'available')),
            'rented_units':      len(units.filtered(lambda u: u.state == 'rented')),
            'sold_units':        len(units.filtered(lambda u: u.state == 'sold')),
            'booked_units':      len(units.filtered(lambda u: u.state == 'booked')),
            'maintenance_units': len(units.filtered(lambda u: u.state == 'maintenance')),
        })
        total = res['total_units']
        occupied = res['rented_units'] + res['sold_units'] + res['booked_units']
        res['occupancy_rate'] = (occupied / total * 100.0) if total else 0.0

        active_rc = RentalContract.search([('state', '=', 'active')])
        res['active_contracts'] = len(active_rc)
        res['expiring_30d'] = len(active_rc.filtered(lambda c: c.date_end and today <= c.date_end <= in_30d))
        res['active_sales'] = SalesContract.search_count([('state', 'in', ['booked', 'spa'])])

        invoices = Invoice.search([('move_type', '=', 'out_invoice'), ('state', '!=', 'cancel')])
        ytd_inv = invoices.filtered(lambda i: i.invoice_date and i.invoice_date >= year_start)
        mtd_inv = invoices.filtered(lambda i: i.invoice_date and i.invoice_date >= month_start)
        draft_inv = invoices.filtered(lambda i: i.state == 'draft')
        overdue_inv = invoices.filtered(lambda i: i.payment_state not in ('paid', 'in_payment') and i.state == 'posted' and i.invoice_date_due and i.invoice_date_due < today)
        res['revenue_ytd']      = sum(ytd_inv.filtered(lambda i: i.state == 'posted').mapped('amount_total'))
        res['revenue_mtd']      = sum(mtd_inv.filtered(lambda i: i.state == 'posted').mapped('amount_total'))
        res['pending_invoices'] = sum(draft_inv.mapped('amount_total'))
        res['overdue_invoices'] = sum(overdue_inv.mapped('amount_residual'))

        maint_open = Maintenance.search([('state', 'in', ['new', 'assigned', 'in_progress'])])
        res['open_maintenance']   = len(maint_open)
        res['urgent_maintenance'] = len(maint_open.filtered(lambda m: m.priority == '2'))
        ytd_maint = Maintenance.search([('completion_date', '>=', str(year_start)), ('state', '=', 'done')])
        res['maint_cost_ytd'] = sum(ytd_maint.mapped('actual_cost'))

        comm = Commission.search([])
        res['pending_commissions']  = sum(comm.filtered(lambda c: c.state in ('draft', 'approved')).mapped('total_with_vat'))
        res['paid_commissions_ytd'] = sum(comm.filtered(lambda c: c.state == 'paid' and c.date and c.date >= year_start).mapped('total_with_vat'))

        return res

    def action_refresh(self):
        new = self.env['property.dashboard'].create({})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'property.dashboard',
            'view_mode': 'form',
            'res_id': new.id,
            'target': 'main',
            'flags': {'mode': 'readonly'},
        }
