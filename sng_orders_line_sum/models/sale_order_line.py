# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    line_number = fields.Integer(
        string="N°",
        compute="_compute_line_number",
        store=False,
    )

    @api.depends(
        "order_id",
        "order_id.order_line",
        "order_id.order_line.sequence",
        "order_id.order_line.display_type",
        "order_id.order_line.product_type",
    )
    def _compute_line_number(self):
        self.filtered(lambda line: not line.order_id).line_number = 0

        for order in self.mapped("order_id"):
            line_number = 0
            for line in order.order_line.sorted(key=lambda order_line: order_line.sequence):
                if line.display_type or line.product_type == "combo":
                    line.line_number = 0
                    continue
                line_number += 1
                line.line_number = line_number
