# -*- coding: utf-8 -*-

from odoo import Command
from odoo.tests.common import TransactionCase


class TestPartnerImportBillExpense(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.fetchmail_server = cls.env["fetchmail.server"]

        cls.fallback_account = cls.env["account.account"].create(
            {
                "name": "Fallback Import Expense",
                "code": "XIMP001",
                "account_type": "expense",
                "company_ids": [Command.set([cls.company.id])],
            }
        )
        cls.partner_account = cls.env["account.account"].create(
            {
                "name": "Partner Import Expense",
                "code": "XIMP002",
                "account_type": "expense_direct_cost",
                "company_ids": [Command.set([cls.company.id])],
            }
        )
        cls.payable_account = cls.env["account.account"].create(
            {
                "name": "Partner Payable Import",
                "code": "XIMP003",
                "account_type": "liability_payable",
                "company_ids": [Command.set([cls.company.id])],
            }
        )
        cls.purchase_journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not cls.purchase_journal:
            cls.purchase_journal = cls.env["account.journal"].create(
                {
                    "name": "Purchase Import Test",
                    "code": "XPI",
                    "type": "purchase",
                    "company_id": cls.company.id,
                }
            )

        cls.vendor_with_account = cls.env["res.partner"].create(
            {
                "name": "Proveedor con cuenta",
                "supplier_rank": 1,
                "import_bill_expense_account_id": cls.partner_account.id,
                "property_account_payable_id": cls.payable_account.id,
            }
        )
        cls.vendor_without_account = cls.env["res.partner"].create(
            {
                "name": "Proveedor sin cuenta",
                "supplier_rank": 1,
                "property_account_payable_id": cls.payable_account.id,
            }
        )

    def _create_vendor_bill(self, partner, move_type="in_invoice"):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "journal_id": self.purchase_journal.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Linea importada",
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.fallback_account.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Nota",
                            "display_type": "line_note",
                        }
                    ),
                ],
            }
        )

    def test_partner_account_overrides_fallback_for_imported_bill(self):
        invoice = self._create_vendor_bill(self.vendor_with_account)

        self.fetchmail_server._apply_partner_import_bill_expense_account(invoice)

        product_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        note_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "line_note"
        )

        self.assertTrue(product_lines)
        self.assertEqual(product_lines.account_id, self.partner_account)
        self.assertFalse(note_lines.account_id)

    def test_fallback_account_is_kept_when_partner_has_no_account(self):
        invoice = self._create_vendor_bill(self.vendor_without_account)

        self.fetchmail_server._apply_partner_import_bill_expense_account(invoice)

        product_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(product_lines.account_id, self.fallback_account)

    def test_partner_account_applies_to_vendor_refund(self):
        refund = self._create_vendor_bill(
            self.vendor_with_account,
            move_type="in_refund",
        )

        self.fetchmail_server._apply_partner_import_bill_expense_account(refund)

        product_lines = refund.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(product_lines.account_id, self.partner_account)

    def test_partner_account_applies_when_account_is_computed(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor_with_account.id,
                "journal_id": self.purchase_journal.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Linea manual",
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.fallback_account.id,
                        }
                    ),
                ],
            }
        )

        product_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(product_lines.account_id, self.partner_account)
