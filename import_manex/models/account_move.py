# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    use_landed_cost = fields.Boolean(string='Usado en Costo de Importación', compute='_compute_use_landed_cost',
                                     store=True)

    def _compute_use_landed_cost(self):
        for move in self:
            move.use_landed_cost = bool(move.line_ids.filtered(lambda line: line.stock_landed_cost_id))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    stock_landed_cost_id = fields.Many2one('stock.landed.cost', string='Costo de Importación', ondelete='restrict')
