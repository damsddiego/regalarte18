# -*- coding: utf-8 -*-

from unittest import SkipTest

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCardSettlement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.bank_journal = cls.env["account.journal"].search([
            ("type", "=", "bank"),
            ("company_id", "=", cls.company.id),
        ], limit=1)
        cls.sale_journal = cls.env["account.journal"].search([
            ("type", "=", "sale"),
            ("company_id", "=", cls.company.id),
        ], limit=1)
        cls.inbound_method_line = cls.bank_journal.inbound_payment_method_line_ids[:1]
        cls.inbound_method_line.is_card_settlement = True
        cls.settlement_bank_account = cls.bank_journal.default_account_id.copy({
            "name": "Cuenta banco liquidacion tarjeta",
        })
        cls.settlement_bank_journal = cls.bank_journal.copy({
            "name": "Banco liquidacion tarjeta test",
            "code": "BLTT",
            "default_account_id": cls.settlement_bank_account.id,
        })
        cls.secondary_bridge_account = cls.inbound_method_line.payment_account_id.copy({
            "name": "Cuenta puente tarjeta secundaria",
        })
        cls.deduction_account = cls.inbound_method_line.payment_account_id.copy({
            "name": "Cuenta deducción tarjeta",
        })
        cls.unallowed_deduction_account = cls.inbound_method_line.payment_account_id.copy({
            "name": "Cuenta no permitida liquidación tarjeta",
        })
        cls.secondary_inbound_method_line = cls.env["account.payment.method.line"].create({
            "name": "Tarjeta Secundaria",
            "payment_method_id": cls.inbound_method_line.payment_method_id.id,
            "journal_id": cls.bank_journal.id,
            "payment_account_id": cls.secondary_bridge_account.id,
            "sequence": cls.inbound_method_line.sequence + 1,
            "is_card_settlement": True,
        })
        cls.unconfigured_source_journal = cls.bank_journal.copy({
            "name": "Otro cobro tarjeta test",
            "code": "OCTT",
        })
        cls.unconfigured_method_line = cls.env["account.payment.method.line"].create({
            "name": "Tarjeta no configurada",
            "payment_method_id": cls.inbound_method_line.payment_method_id.id,
            "journal_id": cls.unconfigured_source_journal.id,
            "payment_account_id": cls.inbound_method_line.payment_account_id.id,
            "sequence": cls.inbound_method_line.sequence + 2,
            "is_card_settlement": True,
        })
        cls.company.write({
            "card_settlement_source_journal_ids": [Command.set(cls.bank_journal.ids)],
            "card_settlement_bank_journal_ids": [Command.set(cls.settlement_bank_journal.ids)],
            "card_settlement_bridge_account_ids": [Command.set((
                cls.inbound_method_line.payment_account_id | cls.secondary_bridge_account
            ).ids)],
            "card_settlement_deduction_account_ids": [Command.set(cls.deduction_account.ids)],
        })

    def _get_open_invoices(self, count):
        currency = self.bank_journal.currency_id or self.company.currency_id
        invoices = self.env["account.move"].search([
            ("company_id", "=", self.company.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
            ("amount_residual", ">", 0.0),
            ("currency_id", "=", currency.id),
            ("partner_id", "!=", False),
        ], limit=count)
        if len(invoices) < count:
            raise SkipTest("No hay suficientes facturas abiertas en RegalarteTest para ejecutar esta prueba.")
        return invoices

    def _register_card_payment(self, invoice, payment_method_line=None, journal=None):
        payment_method_line = payment_method_line or self.inbound_method_line
        journal = journal or payment_method_line.journal_id
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=invoice.ids,
        ).create({
            "journal_id": journal.id,
            "payment_method_line_id": payment_method_line.id,
            "amount": invoice.amount_total,
        })
        return wizard._create_payments()

    def test_card_payment_marks_invoice_paid(self):
        invoice = self._get_open_invoices(1)
        payment = self._register_card_payment(invoice)

        invoice.invalidate_recordset(["payment_state"])
        self.assertTrue(payment.is_card_settlement_required)
        self.assertEqual(invoice.payment_state, "paid")
        self.assertTrue(payment.is_matched)

        liquidity_lines, _counterpart_lines, _writeoff_lines = payment._seek_for_lines()
        self.assertEqual(liquidity_lines.account_id, self.inbound_method_line.payment_account_id)

    def test_wizard_only_proposes_unsettled_card_payments(self):
        eligible_invoice, linked_invoice = self._get_open_invoices(2)
        eligible_payment = self._register_card_payment(eligible_invoice)
        linked_payment = self._register_card_payment(
            linked_invoice,
            self.secondary_inbound_method_line,
        )

        settlement = self.env["sng.card.settlement"].create({
            "journal_id": self.settlement_bank_journal.id,
            "transaction_date": linked_payment.date,
            "settlement_date": linked_payment.date,
        })
        linked_payment.card_settlement_id = settlement.id

        wizard = self.env["sng.card.settlement.wizard"].create({
            "journal_id": self.settlement_bank_journal.id,
            "transaction_date": eligible_payment.date,
            "settlement_date": eligible_payment.date,
        })
        proposed_payments = wizard._get_eligible_payments()

        self.assertIn(eligible_payment, proposed_payments)
        self.assertNotIn(linked_payment, proposed_payments)

    def test_wizard_rejects_manually_selected_payment_from_unconfigured_journal(self):
        eligible_invoice, invalid_invoice = self._get_open_invoices(2)
        eligible_payment = self._register_card_payment(eligible_invoice)
        invalid_payment = self._register_card_payment(
            invalid_invoice,
            self.unconfigured_method_line,
            self.unconfigured_source_journal,
        )

        wizard = self.env["sng.card.settlement.wizard"].create({
            "journal_id": self.settlement_bank_journal.id,
            "transaction_date": eligible_payment.date,
            "settlement_date": fields.Date.today(),
            "payment_ids": [Command.set((eligible_payment | invalid_payment).ids)],
        })

        self.assertNotIn(invalid_payment, wizard._get_eligible_payments())
        with self.assertRaises(UserError):
            wizard.action_generate_settlement()

    def test_settlement_rejects_deduction_account_not_configured(self):
        invoice = self._get_open_invoices(1)
        payment = self._register_card_payment(invoice)

        wizard = self.env["sng.card.settlement.wizard"].create({
            "journal_id": self.settlement_bank_journal.id,
            "transaction_date": payment.date,
            "settlement_date": fields.Date.today(),
            "payment_ids": [Command.set(payment.ids)],
            "deduction_ids": [
                Command.create({
                    "name": "Comisión no configurada",
                    "account_id": self.unallowed_deduction_account.id,
                    "amount": 10.0,
                }),
            ],
        })

        with self.assertRaises(UserError):
            wizard.action_generate_settlement()

    def test_settlement_posts_single_move_and_reconciles_multiple_bridge_accounts(self):
        invoice_a, invoice_b = self._get_open_invoices(2)
        payment_a = self._register_card_payment(invoice_a, self.inbound_method_line)
        payment_b = self._register_card_payment(invoice_b, self.secondary_inbound_method_line)

        wizard = self.env["sng.card.settlement.wizard"].create({
            "journal_id": self.settlement_bank_journal.id,
            "transaction_date": payment_a.date,
            "settlement_date": fields.Date.today(),
            "payment_ids": [Command.set((payment_a | payment_b).ids)],
            "deduction_ids": [
                Command.create({
                    "name": "Comisión",
                    "account_id": self.deduction_account.id,
                    "amount": 10.0,
                }),
            ],
        })
        action = wizard.action_generate_settlement()
        settlement = self.env["sng.card.settlement"].browse(action["res_id"])

        self.assertEqual(settlement.state, "posted")
        self.assertEqual(settlement.move_id.state, "posted")
        self.assertEqual(settlement.gross_amount, payment_a.amount + payment_b.amount)
        self.assertEqual(settlement.deduction_amount, 10.0)
        self.assertEqual(settlement.net_amount, settlement.gross_amount - 10.0)
        self.assertEqual(payment_a.card_settlement_id, settlement)
        self.assertEqual(payment_b.card_settlement_id, settlement)

        bridge_lines = settlement.move_id.line_ids.filtered(
            lambda line: line.account_id in (
                self.inbound_method_line.payment_account_id,
                self.secondary_bridge_account,
            ) and line.credit > 0.0
        )
        self.assertEqual(len(bridge_lines), 2)

        bank_line = settlement.move_id.line_ids.filtered(
            lambda line: line.account_id == self.settlement_bank_journal.default_account_id and line.debit > 0.0
        )[:1]
        self.assertEqual(bank_line.debit, settlement.net_amount)

        liquidity_a, _counterpart_a, _writeoff_a = payment_a._seek_for_lines()
        liquidity_b, _counterpart_b, _writeoff_b = payment_b._seek_for_lines()
        self.assertTrue(all(line.reconciled for line in liquidity_a))
        self.assertTrue(all(line.reconciled for line in liquidity_b))
