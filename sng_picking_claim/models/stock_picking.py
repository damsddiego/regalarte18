# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "sng.picking.claim.mixin"]

    sng_claim_ids = fields.One2many(
        "sng.picking.claim",
        "picking_id",
        string="Historial de alistado",
        readonly=True,
    )
    sng_claim_count = fields.Integer(
        string="Reclamos",
        compute="_compute_sng_claim_count",
    )

    def _compute_sng_claim_count(self):
        grouped = self.env["sng.picking.claim"]._read_group(
            [("picking_id", "in", self.ids)],
            ["picking_id"],
            ["__count"],
        )
        counts = {picking.id: count for picking, count in grouped}
        for picking in self:
            picking.sng_claim_count = counts.get(picking.id, 0)
