from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain=[('customer_rank', '>', 0)],
        help="Customer associated with this location. Used for customer location tracking."
    )
