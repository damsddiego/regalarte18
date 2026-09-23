# -*- coding: utf-8 -*-
from odoo import api, models


class InventoryAdjustmentRequest(models.Model):
    _inherit = "sng.inventory.adjustment.request"

    @api.model_create_multi
    def create(self, vals_list):
        quants = self.env["stock.quant"].browse([v.get("quant_id") for v in vals_list if v.get("quant_id")])
        quants._cycle_lock()
        quants._cycle_check_no_session()
        return super().create(vals_list)

    def action_submit(self):
        self.quant_id._cycle_lock()
        self.quant_id._cycle_check_no_session()
        return super().action_submit()

    def action_approve(self):
        self.quant_id._cycle_lock()
        self.quant_id._cycle_check_no_session()
        return super().action_approve()
