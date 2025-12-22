# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from collections import defaultdict


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    purchase_ids = fields.One2many('purchase.order', 'stock_landed_cost_id', string='Orden de Compra')

    move_line_ids = fields.One2many('account.move.line', 'stock_landed_cost_id', string='Movimientos Contables',
                                    copy=False)

    ref = fields.Text(string='Referencia')

    move_ids = fields.Many2many('account.move', string='Movimientos Contables')

    @api.onchange('purchase_ids')
    def _onchange_purchase_ids(self):
        if self.purchase_ids:
            pickings = self.env['stock.picking'].search([
                ('purchase_id', 'in', self.purchase_ids.ids),
                ('state', '=', 'done')
            ])
            self.picking_ids = [(6, 0, pickings.ids)]
        else:
            self.picking_ids = [(6, 0, [])]

    def buscar_movimientos(self):
        if self.move_ids:
            for move in self.move_ids:
                move.line_ids.filtered(lambda line: not line.credit and line.tax_ids).write(
                    {'stock_landed_cost_id': self.id})

        # Buscar líneas contables relacionadas con el 'landed_id'
        # move_line_ids = self.env['account.move.line'].search([('landed_id', '=', self.landed_id.id)])
        landed_product = self.env['product.product'].search([('landed_cost_ok', '=', True)])

        for landed in landed_product:
            total_price = 0.0
            name = ''
            for line in self.move_line_ids:
                total_price += abs(line.balance)
                name = 'Costo de Importación'  # O usa un nombre representativo, si quieres combinar varios

            self.cost_lines = [(5, 0)]  # Limpiar líneas anteriores

            # Agregar solo una línea con el total acumulado
            self.cost_lines = [(0, 0, {
                'product_id': landed.id,
                'name': name,
                'split_method': landed.split_method_landed_cost,
                'price_unit': total_price
            })]

    def get_valuation_summary_by_product(self):
        """Agrupa los ajustes por plantilla de producto (modelo, marca y color).
        Suma cantidades, costos y recalcula nuevo valor."""
        self.ensure_one()
        summary = {}

        for line in self.valuation_adjustment_lines:
            product = line.product_id
            template = product.product_tmpl_id
            key = template.id

            if key not in summary:
                summary[key] = {
                    'template': template,
                    'quantity': line.quantity,
                    'former_cost': line.former_cost,
                    'additional_cost': line.additional_landed_cost,
                }
            else:
                summary[key]['quantity'] += line.quantity
                summary[key]['former_cost'] += line.former_cost
                summary[key]['additional_cost'] += line.additional_landed_cost

        # Calcular nuevo valor
        for entry in summary.values():
            entry['new_cost'] = entry['former_cost'] + entry['additional_cost']

        return list(summary.values())

    def action_print_report(self):
        return self.env.ref('import_manex.report_import_manex').report_action(self)
