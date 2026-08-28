# -*- coding: utf-8 -*-

from odoo import _, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    sng_replenishment_batch_id = fields.Many2one(
        "sng.biweekly.replenishment.batch",
        string="Ciclo de reabastecimiento",
        copy=False,
        index=True,
        ondelete="set null",
    )
    sng_replenishment_source_id = fields.Many2one(
        "sng.biweekly.replenishment.source",
        string="CEDIS de reabastecimiento",
        copy=False,
        ondelete="set null",
    )

    def action_view_replenishment_batch(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ciclo de reabastecimiento"),
            "res_model": "sng.biweekly.replenishment.batch",
            "res_id": self.sng_replenishment_batch_id.id,
            "view_mode": "form",
            "target": "current",
        }


class StockMove(models.Model):
    _inherit = "stock.move"

    sng_replenishment_line_id = fields.Many2one(
        "sng.biweekly.replenishment.line",
        string="Línea de reabastecimiento",
        copy=False,
        index=True,
        ondelete="set null",
    )

