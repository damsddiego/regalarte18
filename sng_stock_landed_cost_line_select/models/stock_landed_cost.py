# -*- coding: utf-8 -*-
from odoo import api, fields, models

class StockLandedCost(models.Model):
    _inherit = "stock.landed.cost"

    selected_move_ids = fields.Many2many(
        comodel_name="stock.move",
        relation="stock_landed_cost_selected_move_rel",
        column1="landed_cost_id",
        column2="move_id",
        string="Líneas objetivo",
        help=(
            "Si se especifican, los costos de destino se aplicarán solo a estas líneas (stock.moves). "
            "Si no se especifican, se aplicarán a todas las líneas de los pickings seleccionados."
        ),
        domain="[('state','=','done'), ('picking_id', 'in', picking_ids)]",
    )

    @api.onchange('selected_move_ids')
    def _onchange_selected_move_ids(self):
        if self.selected_move_ids:
            self.picking_ids = [(6, 0, list(set(self.selected_move_ids.mapped('picking_id').ids)))]

    def _get_targeted_move_lines(self):
        moves = super()._get_targeted_move_lines()
        if self.selected_move_ids:
            move_ids = set(self.selected_move_ids.ids)
            moves = moves.filtered(lambda m: m.id in move_ids)
        return moves

    def _get_valuation_lines_data(self):
        data = super()._get_valuation_lines_data()
        if self.selected_move_ids and data:
            selected = set(self.selected_move_ids.ids)
            filtered = []
            for d in data:
                move = d.get('move_id')
                move_id = move.id if hasattr(move, 'id') else move
                if move_id in selected:
                    filtered.append(d)
            return filtered
        return data

    def _create_accounting_entries(self, move=None):
        res = super()._create_accounting_entries(move=move)
        for rec in self:
            if rec.selected_move_ids and rec.valuation_adjustment_lines:
                targeted = set(rec.selected_move_ids.ids)
                to_keep = rec.valuation_adjustment_lines.filtered(
                    lambda l: getattr(l, 'move_id', False) and l.move_id.id in targeted
                )
                if to_keep and len(to_keep) != len(rec.valuation_adjustment_lines):
                    rec.valuation_adjustment_lines = [(6, 0, to_keep.ids)]
        return res

    def compute_landed_cost(self):
        """
        Override del método compute_landed_cost para considerar solo las líneas seleccionadas
        cuando se especifiquen selected_move_ids
        """
        # cálculo estándar
        res = super().compute_landed_cost()

        # Si hay líneas seleccionadas se recalcula
        for landed_cost in self:
            if not landed_cost.selected_move_ids:
                continue

            # Obtener líneas de valoración
            selected_move_ids = set(landed_cost.selected_move_ids.ids)

            # Filtrar
            valuation_lines = landed_cost.valuation_adjustment_lines.filtered(
                lambda line: line.move_id and line.move_id.id in selected_move_ids
            )

            if not valuation_lines:
                continue

            # Recalcular
            AdjustementLines = self.env['stock.valuation.adjustment.lines']

            # Eliminar existentes
            landed_cost.valuation_adjustment_lines.unlink()

            # crear las líneas solo para los moves seleccionados
            for cost_line in landed_cost.cost_lines:
                if cost_line.product_id:
                    total_qty = 0.0
                    total_cost = 0.0
                    total_weight = 0.0
                    total_volume = 0.0
                    total_line = 0.0

                    # Calcular totales
                    for move in landed_cost.selected_move_ids:
                        move_lines = move.move_line_ids.filtered(lambda ml: ml.qty_done > 0)
                        for move_line in move_lines:
                            total_qty += move_line.qty_done
                            total_cost += move_line.qty_done * move_line.move_id.product_id.standard_price
                            total_weight += move_line.qty_done * move_line.move_id.product_id.weight
                            total_volume += move_line.qty_done * move_line.move_id.product_id.volume
                            total_line += 1

                    # Crear las líneas de ajuste solo para los moves seleccionados
                    for move in landed_cost.selected_move_ids:
                        move_lines = move.move_line_ids.filtered(lambda ml: ml.qty_done > 0)
                        for move_line in move_lines:
                            # Calcular el valor distribuido según el método de split
                            if cost_line.split_method == 'equal':
                                per_unit = cost_line.price_unit / total_line if total_line else 0.0
                                value_split = per_unit
                            elif cost_line.split_method == 'by_quantity':
                                per_unit = cost_line.price_unit / total_qty if total_qty else 0.0
                                value_split = per_unit * move_line.qty_done
                            elif cost_line.split_method == 'by_current_cost_price':
                                per_unit = cost_line.price_unit / total_cost if total_cost else 0.0
                                value_split = per_unit * move_line.qty_done * move_line.move_id.product_id.standard_price
                            elif cost_line.split_method == 'by_weight':
                                per_unit = cost_line.price_unit / total_weight if total_weight else 0.0
                                value_split = per_unit * move_line.qty_done * move_line.move_id.product_id.weight
                            elif cost_line.split_method == 'by_volume':
                                per_unit = cost_line.price_unit / total_volume if total_volume else 0.0
                                value_split = per_unit * move_line.qty_done * move_line.move_id.product_id.volume
                            else:
                                value_split = 0.0

                            # Crear la línea de ajuste de valoración
                            vals = {
                                'product_id': move_line.product_id.id,
                                'move_id': move.id,
                                'quantity': move_line.qty_done,
                                'former_cost': move_line.qty_done * move_line.move_id.product_id.standard_price,
                                'additional_landed_cost': value_split,
                                'cost_line_id': cost_line.id,
                                'cost_id': landed_cost.id,  # Campo obligatorio que faltaba
                                'weight': move_line.qty_done * move_line.move_id.product_id.weight,
                                'volume': move_line.qty_done * move_line.move_id.product_id.volume,
                            }
                            AdjustementLines |= AdjustementLines.create(vals)

            # Asignar las nuevas líneas al landed cost
            landed_cost.valuation_adjustment_lines = AdjustementLines

        return res
