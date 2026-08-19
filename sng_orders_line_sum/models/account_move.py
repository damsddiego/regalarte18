# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    invoice_product_line_count = fields.Integer(
        string="Total líneas de producto",
        compute="_compute_invoice_product_line_totals",
    )
    invoice_product_qty_total = fields.Float(
        string="Cantidad total de productos",
        compute="_compute_invoice_product_line_totals",
        digits="Product Unit of Measure",
    )

    @api.depends(
        "invoice_line_ids",
        "invoice_line_ids.display_type",
        "invoice_line_ids.quantity",
    )
    def _compute_invoice_product_line_totals(self):
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda line: line.display_type == "product"
            )
            move.invoice_product_line_count = len(product_lines)
            move.invoice_product_qty_total = sum(product_lines.mapped("quantity"))
