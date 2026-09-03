# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "sng.picking.claim.mixin"]

    sng_claim_ids = fields.One2many(
        "sng.picking.claim",
        "sale_order_id",
        string="Historial de alistado",
        readonly=True,
    )
    sng_claim_count = fields.Integer(
        string="Reclamos",
        compute="_compute_sng_claim_count",
    )

    def _compute_sng_claim_count(self):
        grouped = self.env["sng.picking.claim"]._read_group(
            [("sale_order_id", "in", self.ids)],
            ["sale_order_id"],
            ["__count"],
        )
        counts = {order.id: count for order, count in grouped}
        for order in self:
            order.sng_claim_count = counts.get(order.id, 0)
