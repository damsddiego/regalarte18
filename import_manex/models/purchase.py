# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    stock_landed_cost_id = fields.Many2one('stock.landed.cost', string='Importación')
