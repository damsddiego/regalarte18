# -*- coding: utf-8 -*-
from odoo import models

class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, *args, **kwargs):
        res = super()._get_stock_move_values(*args, **kwargs)

        values = kwargs.get('values')
        if values is None:
            for a in reversed(args):
                if isinstance(a, dict):
                    values = a
                    break

        partner_loc_id = None
        if isinstance(values, dict):
            partner_loc_id = values.get('partner_sale_location_id')

        if partner_loc_id:
            res['location_id'] = partner_loc_id

        return res
