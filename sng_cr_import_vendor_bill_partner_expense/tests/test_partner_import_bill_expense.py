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
                        }
                    ),
                ],
            }
        )

        product_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(product_lines.account_id, self.partner_account)

    def _product_lines(self, move):
        return move.invoice_line_ids.filtered(lambda line: line.display_type == "product")

    def _create_simple_bill(self, partner, account=None):
        line_vals = {"name": "Linea", "quantity": 1.0, "price_unit": 100.0}
        if account:
            line_vals["account_id"] = account.id
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "journal_id": self.purchase_journal.id,
                "invoice_date": "2026-01-15",
                "invoice_line_ids": [Command.create(line_vals)],
            }
        )

    def test_explicit_account_is_respected_on_create(self):
        """La cuenta del proveedor es una sugerencia: si la línea trae cuenta, se respeta."""
        invoice = self._create_simple_bill(self.vendor_with_account, self.fallback_account)
        self.assertEqual(self._product_lines(invoice).account_id, self.fallback_account)

    def test_changing_partner_account_does_not_rewrite_existing_bills(self):
        """Cambiar la cuenta en la ficha del proveedor no toca facturas existentes."""
        draft = self._create_simple_bill(self.vendor_with_account)
        posted = self._create_simple_bill(self.vendor_with_account)
        posted.ref = "TEST-HIST-001"
        posted.action_post()
        self.assertEqual(posted.state, "posted")
        self.assertEqual(self._product_lines(posted).account_id, self.partner_account)

        self.vendor_with_account.import_bill_expense_account_id = self.fallback_account
        self.env.flush_all()
        self.env.invalidate_all()

        self.assertEqual(self._product_lines(posted).account_id, self.partner_account)
        self.assertEqual(self._product_lines(draft).account_id, self.partner_account)
        # Las facturas nuevas sí toman la cuenta nueva.
        new_bill = self._create_simple_bill(self.vendor_with_account)
        self.assertEqual(self._product_lines(new_bill).account_id, self.fallback_account)

    def test_manual_account_survives_adding_lines(self):
        """Agregar una línea no devuelve a la cuenta del proveedor las ya corregidas."""
        invoice = self._create_simple_bill(self.vendor_with_account)
        first_line = self._product_lines(invoice)
        first_line.account_id = self.fallback_account

        invoice.write(
            {
                "invoice_line_ids": [
                    Command.create({"name": "Otra linea", "quantity": 1.0, "price_unit": 50.0})
                ]
            }
        )

        self.assertEqual(first_line.account_id, self.fallback_account)
        new_line = self._product_lines(invoice) - first_line
        self.assertEqual(new_line.account_id, self.partner_account)

    def test_changing_bill_partner_reapplies_account(self):
        invoice = self._create_simple_bill(self.vendor_without_account, self.fallback_account)
        invoice.partner_id = self.vendor_with_account
        self.assertEqual(self._product_lines(invoice).account_id, self.partner_account)

    def test_button_reapplies_only_to_draft_bills(self):
        draft = self._create_simple_bill(self.vendor_with_account)
        posted = self._create_simple_bill(self.vendor_with_account)
        posted.ref = "TEST-HIST-002"
        posted.action_post()
        self.vendor_with_account.import_bill_expense_account_id = self.fallback_account

        action = self.vendor_with_account.action_apply_import_bill_expense_account_to_drafts()

        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(self._product_lines(draft).account_id, self.fallback_account)
        self.assertEqual(self._product_lines(posted).account_id, self.partner_account)

    def test_storable_real_time_product_keeps_stock_input_account(self):
        """Con valoración automática anglosajona la línea del producto almacenable
        conserva la cuenta puente de compras aunque el proveedor tenga cuenta fija."""
        if "property_valuation" not in self.env["product.category"]._fields:
            self.skipTest("stock_account no instalado")
        self.company.anglo_saxon_accounting = True
        accounts = {}
        for key, code, account_type in (
            ("valuation", "XIMP010", "asset_current"),
            ("input", "XIMP011", "liability_current"),
            ("output", "XIMP012", "asset_current"),
        ):
            accounts[key] = self.env["account.account"].create(
                {
                    "name": "Stock %s" % key,
                    "code": code,
                    "account_type": account_type,
                    "reconcile": key != "valuation",
                    "company_ids": [Command.set([self.company.id])],
                }
            )
        category = self.env["product.category"].create(
            {
                "name": "Mercaderia valoracion automatica",
                "property_valuation": "real_time",
                "property_cost_method": "average",
                "property_stock_valuation_account_id": accounts["valuation"].id,
                "property_stock_account_input_categ_id": accounts["input"].id,
                "property_stock_account_output_categ_id": accounts["output"].id,
            }
        )
        storable = self.env["product.product"].create(
            {"name": "Mercaderia", "is_storable": True, "categ_id": category.id}
        )
        service = self.env["product.product"].create(
            {"name": "Servicio", "type": "service", "categ_id": category.id}
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor_with_account.id,
                "journal_id": self.purchase_journal.id,
                "invoice_line_ids": [
                    Command.create({"product_id": storable.id, "quantity": 1.0, "price_unit": 100.0}),
                    Command.create({"product_id": service.id, "quantity": 1.0, "price_unit": 50.0}),
                ],
            }
        )
        self.fetchmail_server._apply_partner_import_bill_expense_account(invoice)

        storable_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == storable)
        service_line = invoice.invoice_line_ids.filtered(lambda l: l.product_id == service)
        self.assertEqual(storable_line.account_id, accounts["input"])
        self.assertEqual(service_line.account_id, self.partner_account)
