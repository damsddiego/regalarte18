# -*- coding: utf-8 -*-

from odoo import models


class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    def _apply_partner_import_bill_expense_account(self, invoice):
        if not invoice or invoice._name != "account.move":
            return invoice
        invoice._apply_partner_import_bill_expense_account()
        return invoice

    def create_invoice_with_attamecth(self, msg, company_id):
        invoice = super().create_invoice_with_attamecth(msg, company_id)
        return self._apply_partner_import_bill_expense_account(invoice)
