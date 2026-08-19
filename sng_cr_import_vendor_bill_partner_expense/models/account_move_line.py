# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.depends(
        "product_id",
        "partner_id",
        "move_id.partner_id",
        "move_id.partner_id.import_bill_expense_account_id",
    )
    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            if line.move_id.move_type not in ("in_invoice", "in_refund"):
                continue

            expense_account = line.move_id.partner_id.import_bill_expense_account_id
            if not expense_account:
                continue

            if (
                line.display_type == "product"
                and (
                    not line.account_id
                    or line.account_id.account_type
                    not in ("liability_payable", "asset_receivable")
                )
            ):
                line.account_id = expense_account
