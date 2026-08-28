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

