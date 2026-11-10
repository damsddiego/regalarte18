# -*- coding: utf-8 -*-
"""Interés moratorio del estado de cuenta: 4 % mensual simple, solo por
meses completos de atraso (30 días) y solo sobre el saldo vencido de
facturas."""

from datetime import date, timedelta
from unittest import SkipTest
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# Fecha de corte simulada en 2027 para no chocar con los candados de la
# copia de Prod (el asistente real siempre corta a la fecha de hoy).
STATEMENT_DATE = date(2027, 6, 30)


@tagged("post_install", "-at_install")
class TestLateInterest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        company = cls.env.company
        # Publicar sin documento electrónico (sin CABYS ni datos de Hacienda)
        # y sin consumir sequence.DA.
        move_class = type(cls.env["account.move"])
        if hasattr(move_class, "_electronic_documents_disabled"):
            cls.startClassPatcher(
                patch.object(move_class, "_electronic_documents_disabled", lambda self: True)
            )
            cls.startClassPatcher(
                patch.object(move_class, "_next_disabled_document_sequence", lambda self: False)
            )
        if "payment_method_default_id" in company._fields:
            payment_method = cls.env.ref(
                "cr_electronic_invoice.PaymentMethods_1", raise_if_not_found=False
            )
            if payment_method:
                company.payment_method_default_id = payment_method
        cls.income_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        cls.receivable_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "asset_receivable"),
                ("company_ids", "in", company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        cls.product = cls.env["product.product"].search(
            [("active", "=", True), ("sale_ok", "=", True)], limit=1
        )
        if not (cls.income_account and cls.receivable_account and cls.product):
            raise SkipTest("Faltan cuentas o productos para las pruebas.")

        cls.customer = cls.env["res.partner"].create({
            "name": "CLIENTE INTERES PRUEBA S.A.",
            "is_company": True,
            "customer_rank": 1,
            "property_account_receivable_id": cls.receivable_account.id,
            "property_payment_term_id": False,
        })

        # 100.000 con 45 días de atraso y abono de 40.000 -> saldo 60.000,
        # 1 mes completo -> 2.400.
        cls.inv_45 = cls._create_move("out_invoice", 45, 100000.0)
        abono = cls._create_move("out_refund", 45, 40000.0)
        cls._apply_credit(cls.inv_45, abono)
        # 50.000 con 65 días -> 2 meses completos -> 4.000.
        cls.inv_65 = cls._create_move("out_invoice", 65, 50000.0)
        # 30.000 con 29 días -> 0 meses -> sin interés.
        cls.inv_29 = cls._create_move("out_invoice", 29, 30000.0)
        # 20.000 por vencer (vence en 10 días) -> sin interés.
        cls.inv_future = cls._create_move("out_invoice", -10, 20000.0)
        # Nota de crédito abierta de 10.000 vieja -> nunca genera interés.
        cls.nc_open = cls._create_move("out_refund", 90, 10000.0)

    @classmethod
    def _create_move(cls, move_type, days_overdue, amount):
        move_date = STATEMENT_DATE - timedelta(days=days_overdue)
        # Una factura por vencer se fecha antes del corte y vence después.
        invoice_date = min(move_date, STATEMENT_DATE)
        move = cls.env["account.move"].create({
            "move_type": move_type,
            "partner_id": cls.customer.id,
            "invoice_date": invoice_date,
            "date": invoice_date,
            "invoice_payment_term_id": False,
            "currency_id": cls.env.company.currency_id.id,
            "invoice_line_ids": [Command.create({
                "product_id": cls.product.id,
                "name": "Línea prueba interés",
                "account_id": cls.income_account.id,
                "quantity": 1,
                "price_unit": amount,
                "tax_ids": [Command.clear()],
            })],
        })
        move.invoice_date_due = move_date
        move.action_post()
        return move

    @classmethod
    def _apply_credit(cls, invoice, refund):
        credit_line = refund.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        invoice.js_assign_outstanding_line(credit_line.id)

    def _wizard(self, **values):
        values.setdefault("partner_id", self.customer.id)
        values.setdefault("company_id", self.env.company.id)
        values.setdefault("statement_date", STATEMENT_DATE)
        return self.env["sng.customer.statement.client.wizard"].new(values)

    def _group(self, wizard):
        groups = wizard._prepare_currency_groups(
            wizard._get_open_moves(), wizard._get_open_credit_lines()
        )
        self.assertEqual(len(groups), 1)
        return groups[0]

    def _rows_by_document(self, group):
        return {row["document"]: row for row in group["rows"]}

    # ------------------------------------------------------------------
    # Regla del cálculo
    # ------------------------------------------------------------------

    def test_months_are_complete_months_only(self):
        wizard = self._wizard()
        currency = self.env.company.currency_id
        compute = wizard._late_interest_amount
        self.assertEqual(compute(60000.0, 0, currency), 0.0)
        self.assertEqual(compute(60000.0, 29, currency), 0.0)
        self.assertEqual(compute(60000.0, 30, currency), 2400.0)
        self.assertEqual(compute(60000.0, 45, currency), 2400.0)
        self.assertEqual(compute(60000.0, 59, currency), 2400.0)
        self.assertEqual(compute(60000.0, 60, currency), 4800.0)
        self.assertEqual(compute(50000.0, 65, currency), 4000.0)
        # Saldos a favor o en cero nunca generan interés.
        self.assertEqual(compute(-10000.0, 90, currency), 0.0)
        self.assertEqual(compute(0.0, 90, currency), 0.0)

    def test_amount_is_rounded_to_currency(self):
        wizard = self._wizard()
        currency = self.env.company.currency_id
        # 333,33 * 4 % = 13,3332 -> 13,33
        self.assertEqual(wizard._late_interest_amount(333.33, 30, currency), 13.33)

    # ------------------------------------------------------------------
    # Asistente
    # ------------------------------------------------------------------

    def test_interest_disabled_by_default(self):
        wizard = self._wizard()
        self.assertFalse(wizard.apply_late_interest)
        group = self._group(wizard)
        self.assertEqual(group["interest"], 0.0)
        self.assertEqual(group["total_with_interest"], group["balance"])
        for row in group["rows"]:
            self.assertEqual(row["interest"], 0.0)

    def test_interest_only_on_overdue_invoices(self):
        group = self._group(self._wizard(apply_late_interest=True))
        rows = self._rows_by_document(group)

        self.assertAlmostEqual(rows[self.inv_45.name]["balance"], 60000.0)
        self.assertAlmostEqual(rows[self.inv_45.name]["interest"], 2400.0)
        self.assertAlmostEqual(rows[self.inv_65.name]["interest"], 4000.0)
        self.assertAlmostEqual(rows[self.inv_29.name]["interest"], 0.0)
        self.assertAlmostEqual(rows[self.inv_future.name]["interest"], 0.0)
        self.assertAlmostEqual(rows[self.nc_open.name]["interest"], 0.0)

        # Saldo: 60.000 + 50.000 + 30.000 + 20.000 - 10.000 = 150.000
        self.assertAlmostEqual(group["balance"], 150000.0)
        self.assertAlmostEqual(group["interest"], 6400.0)
        self.assertAlmostEqual(group["total_with_interest"], 156400.0)

    def _saved_wizard(self, apply_late_interest):
        """Asistente guardado, como al pulsar Vista previa / Descargar PDF.
        Se omite la validación de fecha de corte = hoy para usar 2027."""
        wizard_class = type(self.env["sng.customer.statement.client.wizard"])
        with patch.object(wizard_class, "_check_statement_date", lambda self: None):
            return self.env["sng.customer.statement.client.wizard"].create({
                "partner_ids": [Command.set(self.customer.ids)],
                "company_id": self.env.company.id,
                "statement_date": STATEMENT_DATE,
                "apply_late_interest": apply_late_interest,
            })

    def test_multi_partner_statement_keeps_option(self):
        statements = self._saved_wizard(True)._prepare_statements_data()
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0]["apply_late_interest"])
        self.assertAlmostEqual(statements[0]["currency_groups"][0]["interest"], 6400.0)

    # ------------------------------------------------------------------
    # Reporte
    # ------------------------------------------------------------------

    def _render(self, apply_late_interest):
        wizard = self._saved_wizard(apply_late_interest)
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "sng_customer_statement_client.action_report_customer_statement_client_html",
            wizard.ids,
        )
        return html.decode()

    def test_report_shows_interest_lines_when_enabled(self):
        html = self._render(True)
        self.assertIn("4% Mensual de interés moratorio", html)
        self.assertIn("Total con intereses", html)
        self.assertIn("6.400,00", html)
        self.assertIn("156.400,00", html)

    def test_report_unchanged_when_disabled(self):
        html = self._render(False)
        self.assertNotIn("interés moratorio", html)
        self.assertNotIn("Total con intereses", html)
