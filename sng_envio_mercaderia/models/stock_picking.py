# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    envio_audit_ids = fields.One2many(
        "sng.envio.mercaderia",
        "picking_id",
        string="Auditorías de envío",
    )
    envio_audit_count = fields.Integer(
        string="Auditorías de envío",
        compute="_compute_envio_audit_count",
    )

    def _compute_envio_audit_count(self):
        grouped = self.env["sng.envio.mercaderia"]._read_group(
            [("picking_id", "in", self.ids)],
            ["picking_id"],
            ["__count"],
        )
        counts = {picking.id: count for picking, count in grouped}
        for picking in self:
            picking.envio_audit_count = counts.get(picking.id, 0)

    def action_view_envio_audits(self):
        self.ensure_one()
        action = self.env.ref(
            "sng_envio_mercaderia.action_envio_mercaderia"
        ).read()[0]
        action["domain"] = [("picking_id", "=", self.id)]
        action["context"] = {
            "default_picking_id": self.id,
            "default_sale_order_id": self.sale_id.id,
            "default_company_id": self.company_id.id,
        }
        return action

