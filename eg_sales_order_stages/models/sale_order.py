from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sale_order_stages = fields.Many2one(
        comodel_name='sale.order.stage',
        string="Stage",
        tracking=True,
        store=True,
        default=lambda self: self.env['sale.order.stage'].search([], order='sequence, id', limit=1),
        group_expand='_read_group_sale_order_stages',
    )

    @api.model
    def _read_group_sale_order_stages(self, stages, domain):
        return stages.search([('show_in_kanban', '=', True)], order=stages._order)
