# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    sng_line_note = fields.Text(string="Nota")

    @api.model_create_multi
    def create(self, vals_list):
        sale_line_ids = {
            vals.get("sale_line_id")
            for vals in vals_list
            if vals.get("sale_line_id") and not vals.get("sng_line_note")
        }
        sale_lines_by_id = {
            line.id: line
            for line in self.env["sale.order.line"].browse(list(sale_line_ids)).exists()
        }
        for vals in vals_list:
            sale_line = sale_lines_by_id.get(vals.get("sale_line_id"))
            if sale_line and sale_line.sng_line_note and not vals.get("sng_line_note"):
                vals["sng_line_note"] = sale_line.sng_line_note
        return super().create(vals_list)
