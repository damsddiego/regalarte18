# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    sng_inventory_adjustment_history_id = fields.Many2one(
        "sng.inventory.adjustment.history",
        string="Historial de ajuste SNG",
        readonly=True,
        copy=False,
        index=True,
        ondelete="set null",
    )
    sng_adjustment_request_id = fields.Many2one(
        "sng.inventory.adjustment.request", string="Solicitud de ajuste",
        readonly=True, copy=False, index=True, ondelete="restrict",
    )

    def _action_done(self, cancel_backorder=False):
        if self.filtered("is_inventory"):
            self.env["stock.quant"]._sng_check_inventory_approval_access()
        return super()._action_done(cancel_backorder=cancel_backorder)
