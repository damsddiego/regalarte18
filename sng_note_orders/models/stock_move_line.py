# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    sng_line_note = fields.Text(string="Nota")

    @api.model_create_multi
    def create(self, vals_list):
        move_ids = {
            vals.get("move_id")
            for vals in vals_list
            if vals.get("move_id") and not vals.get("sng_line_note")
        }
        moves_by_id = {
            move.id: move
            for move in self.env["stock.move"].browse(list(move_ids)).exists()
        }
        for vals in vals_list:
            move = moves_by_id.get(vals.get("move_id"))
            if move and move.sng_line_note and not vals.get("sng_line_note"):
                vals["sng_line_note"] = move.sng_line_note
        return super().create(vals_list)
