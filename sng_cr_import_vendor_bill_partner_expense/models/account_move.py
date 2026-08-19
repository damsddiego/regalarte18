# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _apply_partner_import_bill_expense_account(self):
        for move in self:
            if move.state != "draft":
                continue
            if move.move_type not in ("in_invoice", "in_refund"):
                continue

            expense_account = move.partner_id.import_bill_expense_account_id
            if not expense_account:
                continue

            product_lines = move.invoice_line_ids.filtered(
                lambda line: line.display_type == "product"
                and (
                    not line.account_id
                    or line.account_id.account_type
                    not in ("liability_payable", "asset_receivable")
                )
            )
            if product_lines:
                product_lines.write({"account_id": expense_account.id})

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._apply_partner_import_bill_expense_account()
        return moves

    def write(self, vals):
        result = super().write(vals)
        if {"partner_id", "invoice_line_ids", "move_type"} & set(vals):
            self._apply_partner_import_bill_expense_account()
        return result
