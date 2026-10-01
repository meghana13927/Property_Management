from odoo import api, fields, models


class PropertyBuilding(models.Model):
    _name = 'property.building'
    _description = 'Building'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Building Name', required=True, tracking=True)
    building_no = fields.Char(string='Building Number', tracking=True)
    code = fields.Char(string='Building Code')
    building_type = fields.Selection([
        ('residential_tower', 'Residential Tower'),
        ('commercial_tower',  'Commercial Tower'),
        ('mixed_use',         'Mixed Use'),
        ('villa_compound',    'Villa Compound'),
        ('office_building',   'Office Building'),
        ('shopping_mall',     'Shopping Mall'),
        ('warehouse_complex', 'Warehouse Complex'),
        ('land_plot',         'Land Plot'),
    ], string='Building Type', required=True, default='residential_tower', tracking=True)

    # Location
    street = fields.Char(string='Street / District')
    city = fields.Char(string='City', tracking=True)
    state_id = fields.Many2one('res.country.state', string='State / Region')
    country_id = fields.Many2one('res.country', string='Country')
    zip_code = fields.Char(string='ZIP')

    # Details
    developer_id = fields.Many2one('res.partner', string='Developer')
    owner_id = fields.Many2one('res.partner', string='Building Owner')
    total_floors = fields.Integer(string='Total Floors')
    year_built = fields.Integer(string='Year Built')
    total_area_sqft = fields.Float(string='Total Area (sqft)')
    description = fields.Html(string='Description')
    image = fields.Image(string='Building Image', max_width=1920, max_height=1920)
    active = fields.Boolean(default=True)

    # Units
    unit_ids = fields.One2many('property.unit', 'building_id', string='Units')

    # Computed stats
    unit_count      = fields.Integer(compute='_compute_unit_stats', store=True, string='Total Units')
    available_count = fields.Integer(compute='_compute_unit_stats', store=True, string='Available')
    rented_count    = fields.Integer(compute='_compute_unit_stats', store=True, string='Rented')
    sold_count      = fields.Integer(compute='_compute_unit_stats', store=True, string='Sold')
    booked_count    = fields.Integer(compute='_compute_unit_stats', store=True, string='Booked')
    maintenance_count = fields.Integer(compute='_compute_unit_stats', store=True, string='Maintenance')
    occupancy_rate  = fields.Float(compute='_compute_unit_stats', store=True, string='Occupancy %', digits=(5, 1))

    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    @api.depends('unit_ids', 'unit_ids.state')
    def _compute_unit_stats(self):
        for rec in self:
            units = rec.unit_ids
            total = len(units)
            avail = len(units.filtered(lambda u: u.state == 'available'))
            rented = len(units.filtered(lambda u: u.state == 'rented'))
            sold = len(units.filtered(lambda u: u.state == 'sold'))
            booked = len(units.filtered(lambda u: u.state == 'booked'))
            maint = len(units.filtered(lambda u: u.state == 'maintenance'))
            occupied = rented + sold + booked
            rec.unit_count = total
            rec.available_count = avail
            rec.rented_count = rented
            rec.sold_count = sold
            rec.booked_count = booked
            rec.maintenance_count = maint
            rec.occupancy_rate = (occupied / total * 100.0) if total else 0.0

    def action_view_units(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Units',
            'res_model': 'property.unit',
            'view_mode': 'kanban,list,form',
            'domain': [('building_id', '=', self.id)],
            'context': {'default_building_id': self.id},
        }
