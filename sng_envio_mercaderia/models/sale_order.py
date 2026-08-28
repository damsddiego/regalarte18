# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    envio_audit_ids = fields.One2many(
        "sng.envio.mercaderia",
        "sale_order_id",
        string="Auditorías de envío",
    )
    envio_audit_count = fields.Integer(
        string="Auditorías de envío",
        compute="_compute_envio_audit_count",
    )

    def _compute_envio_audit_count(self):
        grouped = self.env["sng.envio.mercaderia"]._read_group(
            [("sale_order_id", "in", self.ids)],
            ["sale_order_id"],
            ["__count"],
        )
        counts = {sale_order.id: count for sale_order, count in grouped}
        for order in self:
            order.envio_audit_count = counts.get(order.id, 0)

    def action_view_envio_audits(self):
        self.ensure_one()
        action = self.env.ref(
            "sng_envio_mercaderia.action_envio_mercaderia"
        ).read()[0]
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {
            "default_sale_order_id": self.id,
            "default_company_id": self.company_id.id,
        }
        return action

