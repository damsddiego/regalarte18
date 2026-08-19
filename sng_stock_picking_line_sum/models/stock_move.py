# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    line_number = fields.Integer(
        string="N°",
        compute="_compute_line_number",
        store=False,
    )

    @api.depends(
        "picking_id",
        "picking_id.move_ids",
        "picking_id.move_ids.sequence",
        "picking_id.move_ids.package_level_id",
        "picking_id.picking_type_entire_packs",
    )
    def _compute_line_number(self):
        self.line_number = 0

        for picking in self.mapped("picking_id"):
            for index, move in enumerate(
                picking.move_ids_without_package.sorted(
                    key=lambda picking_move: picking_move.sequence
                ),
                start=1,
            ):
                move.line_number = index
