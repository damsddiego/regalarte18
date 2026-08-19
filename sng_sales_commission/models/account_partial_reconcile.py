# -*- coding: utf-8 -*-

from odoo import api, models


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def _get_related_commission_settlements(self):
        settlements = self.env["sng.commission.settlement"]
        for partial in self:
            invoice_move = False
            if partial.debit_move_id.move_id.move_type == "out_invoice":
                invoice_move = partial.debit_move_id.move_id
            elif partial.credit_move_id.move_id.move_type == "out_invoice":
                invoice_move = partial.credit_move_id.move_id
            if not invoice_move:
                continue
            salesperson = invoice_move.salesperson_id or invoice_move.partner_id.assigned_salesperson_id
            if not salesperson or not partial.max_date:
                continue
            settlements |= self.env["sng.commission.settlement"].search(
                [
                    ("company_id", "=", partial.company_id.id),
                    ("salesperson_id", "=", salesperson.id),
                    ("year", "=", partial.max_date.year),
                    ("month", "=", str(partial.max_date.month)),
                    ("state", "=", "draft"),
                ]
            )
        return settlements

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        partials._get_related_commission_settlements()._mark_needs_recompute()
        return partials

    def unlink(self):
        settlements = self._get_related_commission_settlements()
        res = super().unlink()
        settlements._mark_needs_recompute()
        return res
