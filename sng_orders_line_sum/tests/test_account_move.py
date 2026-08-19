# -*- coding: utf-8 -*-

from unittest import SkipTest

from odoo import Command
from odoo.tests import TransactionCase


class TestAccountMoveLineTotals(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.income_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", cls.env.company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        cls.receivable_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "asset_receivable"),
                ("company_ids", "in", cls.env.company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        if not cls.income_account or not cls.receivable_account:
            raise SkipTest("No active income and receivable accounts are available for invoice tests.")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Invoice Totals Customer",
                "property_account_receivable_id": cls.receivable_account.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Invoice Totals Product",
                "list_price": 10.0,
            }
        )

    def _create_invoice(self):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "account_id": self.income_account.id,
                            "quantity": 2.0,
                            "price_unit": 10.0,
                        }
                    ),
                    Command.create(
                        {
                            "display_type": "line_section",
                            "name": "Section",
                        }
                    ),
                    Command.create(
                        {
                            "display_type": "line_note",
                            "name": "Note",
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "account_id": self.income_account.id,
                            "quantity": 3.5,
                            "price_unit": 10.0,
                        }
                    ),
                ],
            }
        )

    def test_invoice_totals_only_include_product_lines(self):
        invoice = self._create_invoice()

        self.assertEqual(invoice.invoice_product_line_count, 2)
        self.assertEqual(invoice.invoice_product_qty_total, 5.5)

    def test_invoice_totals_recompute_after_line_changes(self):
        invoice = self._create_invoice()
        product_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )

        product_lines[0].quantity = 4.0
        product_lines[1].unlink()

        self.assertEqual(invoice.invoice_product_line_count, 1)
        self.assertEqual(invoice.invoice_product_qty_total, 4.0)
