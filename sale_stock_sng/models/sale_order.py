# -*- coding: utf-8 -*-
from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_sale_location_id = fields.Many2one(
        'stock.location',
        string='Ubicación salida (cliente)'
    )

    @api.onchange('partner_id')
    def _onchange_partner_sale_location(self):
        self.partner_sale_location_id = self.partner_id.sale_location_id

    def _prepare_procurement_values(self, group_id=False):
        vals = super()._prepare_procurement_values(group_id=group_id)
        if self.partner_sale_location_id:
            vals['partner_sale_location_id'] = self.partner_sale_location_id.id
        return vals


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_procurement_values(self, group_id=False):
        vals = super()._prepare_procurement_values(group_id=group_id)
        partner_loc = self.order_id.partner_id.sale_location_id
        if partner_loc:
            vals['partner_sale_location_id'] = partner_loc.id
        return vals
