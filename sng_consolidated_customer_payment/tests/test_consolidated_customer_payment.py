# -*- coding: utf-8 -*-

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestConsolidatedCustomerPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_data_2 = cls.setup_other_company(name="company_consolidated_2")
        cls.company_2 = cls.company_data_2["company"]

        cls.partner_shared = cls.env["res.partner"].create({
            "name": "Cliente consolidado",
            "invoice_sending_method": "manual",
            "invoice_edi_format": False,
            "company_id": False,
        })
        cls.partner_shared.with_company(cls.env.company).property_account_receivable_id = cls.company_data["default_account_receivable"]
        cls.partner_shared.with_company(cls.env.company).property_account_payable_id = cls.company_data["default_account_payable"]
        cls.partner_shared.with_company(cls.company_2).property_account_receivable_id = cls.company_data_2["default_account_receivable"]
        cls.partner_shared.with_company(cls.company_2).property_account_payable_id = cls.company_data_2["default_account_payable"]

        cls.bridge_account_1 = cls.copy_account(cls.company_data["default_account_receivable"])
        cls.bridge_account_1.write({
            "name": "Bridge To Company 2",
            "code": "BRG01",
            "account_type": "liability_current",
            "reconcile": True,
        })
        cls.bridge_account_2 = cls.copy_account(cls.company_data_2["default_account_receivable"])
        cls.bridge_account_2.write({
            "name": "Bridge From Company 1",
            "code": "BRG02",
            "account_type": "asset_current",
            "reconcile": True,
        })

        cls.bridge_1 = cls.env["consolidated.customer.payment.bridge"].create({
            "company_id": cls.env.company.id,
            "counterpart_company_id": cls.company_2.id,
            "journal_id": cls.company_data["default_journal_misc"].id,
            "bridge_account_id": cls.bridge_account_1.id,
        })
        cls.bridge_2 = cls.env["consolidated.customer.payment.bridge"].create({
            "company_id": cls.company_2.id,
            "counterpart_company_id": cls.env.company.id,
            "journal_id": cls.company_data_2["default_journal_misc"].id,
            "bridge_account_id": cls.bridge_account_2.id,
        })

    def _create_customer_invoice(self, company, amount):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_shared,
            amounts=[amount],
            taxes=[],
            company=company,
            post=True,
        )
        return invoice

    def test_post_consolidated_payment_multi_company(self):
        invoice_company_1 = self._create_customer_invoice(self.env.company, 40.0)
        invoice_company_2 = self._create_customer_invoice(self.company_2, 60.0)

        consolidated_payment = self.env["consolidated.customer.payment"].create({
            "company_id": self.env.company.id,
            "payment_date": "2026-04-22",
            "journal_id": self.company_data["default_journal_bank"].id,
            "payment_method_line_id": self.inbound_payment_method_line.id,
            "partner_id": self.partner_shared.id,
            "amount": 100.0,
            "auto_reconcile": True,
            "line_ids": [
                (0, 0, {
                    "sequence": 10,
                    "invoice_move_id": invoice_company_1.id,
                    "residual_amount_at_load": invoice_company_1.amount_residual,
                    "allocated_amount": 40.0,
                }),
                (0, 0, {
                    "sequence": 20,
                    "invoice_move_id": invoice_company_2.id,
                    "residual_amount_at_load": invoice_company_2.amount_residual,
                    "allocated_amount": 60.0,
                }),
            ],
        })

        consolidated_payment.action_confirm()
        consolidated_payment.action_post()

        self.assertEqual(consolidated_payment.state, "posted")
        self.assertEqual(len(consolidated_payment.payment_ids), 1)
        self.assertEqual(len(consolidated_payment.move_ids), 4)
        self.assertEqual(invoice_company_1.amount_residual, 0.0)
        self.assertEqual(invoice_company_2.amount_residual, 0.0)
        self.assertTrue(all(consolidated_payment.line_ids.mapped("is_target_reconciled")))

        payment = consolidated_payment.payment_ids
        receivable_line = payment.move_id.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")
        self.assertTrue(receivable_line.reconciled)

    def test_confirm_requires_bridge_configuration(self):
        invoice_company_2 = self._create_customer_invoice(self.company_2, 60.0)
        self.bridge_1.unlink()

        consolidated_payment = self.env["consolidated.customer.payment"].create({
            "company_id": self.env.company.id,
            "payment_date": "2026-04-22",
            "journal_id": self.company_data["default_journal_bank"].id,
            "payment_method_line_id": self.inbound_payment_method_line.id,
            "partner_id": self.partner_shared.id,
            "amount": 60.0,
            "line_ids": [
                (0, 0, {
                    "sequence": 10,
                    "invoice_move_id": invoice_company_2.id,
                    "residual_amount_at_load": invoice_company_2.amount_residual,
                    "allocated_amount": 60.0,
                }),
            ],
        })

        with self.assertRaisesRegex(Exception, "puente intercompany"):
            consolidated_payment.action_confirm()

    def test_load_wizard_respects_existing_open_invoices(self):
        invoice_company_1 = self._create_customer_invoice(self.env.company, 25.0)
        payment = self.env["consolidated.customer.payment"].create({
            "company_id": self.env.company.id,
            "payment_date": "2026-04-22",
            "journal_id": self.company_data["default_journal_bank"].id,
            "payment_method_line_id": self.inbound_payment_method_line.id,
            "partner_id": self.partner_shared.id,
            "amount": 25.0,
        })

        wizard = self.env["consolidated.customer.payment.load.wizard"].create({
            "payment_id": payment.id,
            "company_ids": [(6, 0, [self.env.company.id])],
            "clear_existing_lines": True,
            "auto_allocate": True,
        })
        wizard.action_load()

        self.assertEqual(payment.line_ids.invoice_move_id, invoice_company_1)
        self.assertEqual(payment.line_ids.allocated_amount, 25.0)
