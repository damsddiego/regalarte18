# -*- coding: utf-8 -*-

import calendar
from datetime import date
from unittest import SkipTest

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged("post_install", "-at_install")
class TestSalesCommission(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.test_year = fields.Date.today().year
        cls.test_month = fields.Date.today().month
        cls.test_month_str = str(cls.test_month)

        cls.bank_journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        cls.inbound_method_line = cls.bank_journal.inbound_payment_method_line_ids[:1]
        cls.receivable_account = cls.env["account.account"].search(
            [("account_type", "=", "asset_receivable"), ("company_ids", "in", cls.company.id)],
            limit=1,
        )
        cls.payable_account = cls.env["account.account"].search(
            [("account_type", "=", "liability_payable"), ("company_ids", "in", cls.company.id)],
            limit=1,
        )
        cls.income_account = cls.env["account.account"].search(
            [("account_type", "=", "income"), ("company_ids", "in", cls.company.id), ("deprecated", "=", False)],
            limit=1,
        )
        if not cls.bank_journal or not cls.inbound_method_line or not cls.receivable_account or not cls.payable_account or not cls.income_account:
            raise SkipTest("No hay configuración contable suficiente para ejecutar las pruebas de comisiones.")

        cls.env["sng.commission.plan"].search(
            [
                ("company_id", "=", cls.company.id),
                ("state", "=", "active"),
            ]
        ).write({"state": "archived", "active": False})

        cls.salesperson = cls.env["res.partner"].create(
            {
                "name": "Vendedor comisión",
                "is_salesperson": True,
            }
        )
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Cliente comisión",
                "assigned_salesperson_id": cls.salesperson.id,
                "property_account_receivable_id": cls.receivable_account.id,
                "property_account_payable_id": cls.payable_account.id,
                "company_id": False,
            }
        )

        cls.foreign_currency = cls.env["res.currency"].search(
            [("id", "!=", cls.company.currency_id.id), ("active", "=", True)],
            limit=1,
        )
        if cls.foreign_currency:
            rate_date = date(cls.test_year, cls.test_month, 1)
            existing_rate = cls.env["res.currency.rate"].search(
                [
                    ("currency_id", "=", cls.foreign_currency.id),
                    ("name", "=", rate_date),
                    ("company_id", "in", [False, cls.company.root_id.id]),
                ],
                limit=1,
            )
            if not existing_rate:
                cls.env["res.currency.rate"].create(
                    {
                        "currency_id": cls.foreign_currency.id,
                        "name": rate_date,
                        "company_id": cls.company.root_id.id,
                        "company_rate": 2.0,
                    }
                )

        cls.plan = cls.env["sng.commission.plan"].create(
            {
                "name": f"Plan {cls.test_year}",
                "company_id": cls.company.id,
                "date_start": date(cls.test_year, 1, 1),
                "state": "active",
                "aging_rule_ids": [
                    Command.create({"sequence": 1, "name": "No vencido", "bucket_type": "not_due", "commission_percentage": 2.0}),
                    Command.create({"sequence": 2, "name": "1-45 días", "bucket_type": "overdue", "days_from": 1, "days_to": 45, "commission_percentage": 1.5}),
                    Command.create({"sequence": 3, "name": "46-60 días", "bucket_type": "overdue", "days_from": 46, "days_to": 60, "commission_percentage": 1.0}),
                    Command.create({"sequence": 4, "name": "61-90 días", "bucket_type": "overdue", "days_from": 61, "days_to": 90, "commission_percentage": 0.5}),
                    Command.create({"sequence": 5, "name": "91+ días", "bucket_type": "overdue", "days_from": 91, "days_to": 999, "commission_percentage": 0.0}),
                ],
                "performance_rule_ids": [
                    Command.create({"sequence": 1, "name": "110-119", "percentage_from": 110.0, "percentage_to": 119.9999, "payout_factor": 115.0}),
                    Command.create({"sequence": 2, "name": "100-109", "percentage_from": 100.0, "percentage_to": 109.9999, "payout_factor": 100.0}),
                    Command.create({"sequence": 3, "name": "95-99", "percentage_from": 95.0, "percentage_to": 99.9999, "payout_factor": 95.0}),
                    Command.create({"sequence": 4, "name": "70-94", "percentage_from": 70.0, "percentage_to": 94.9999, "payout_factor": 50.0}),
                    Command.create({"sequence": 5, "name": "0-69", "percentage_from": 0.0, "percentage_to": 69.9999, "payout_factor": 0.0}),
                ],
            }
        )

    @classmethod
    def _make_date(cls, day):
        last_day = calendar.monthrange(cls.test_year, cls.test_month)[1]
        return date(cls.test_year, cls.test_month, min(day, last_day))

    def _create_invoice(self, amount, invoice_date, due_date, currency=None, invoice_user=None):
        values = {
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": invoice_date,
            "date": invoice_date,
            "invoice_date_due": due_date,
            "currency_id": (currency or self.company.currency_id).id,
            "salesperson_id": self.customer.assigned_salesperson_id.id,
            "invoice_line_ids": [
                Command.create(
                    {
                        "name": "Comisión test",
                        "quantity": 1.0,
                        "price_unit": amount,
                        "account_id": self.income_account.id,
                        "tax_ids": [],
                    }
                )
            ],
        }
        if invoice_user:
            values["invoice_user_id"] = invoice_user.id
        invoice = self.env["account.move"].create(
            values
        )
        invoice.action_post()
        return invoice

    def _register_payment(self, invoice, amount, payment_date):
        return self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=invoice.ids,
        ).create(
            {
                "journal_id": self.bank_journal.id,
                "payment_method_line_id": self.inbound_method_line.id,
                "amount": amount,
                "payment_date": payment_date,
            }
        )._create_payments()

    def _register_payment_for_invoices(self, invoices, amount, payment_date):
        return self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=invoices.ids,
        ).create(
            {
                "journal_id": self.bank_journal.id,
                "payment_method_line_id": self.inbound_method_line.id,
                "amount": amount,
                "payment_date": payment_date,
            }
        )._create_payments()

    def _reverse_invoice(self, invoice):
        return invoice._reverse_moves(cancel=True)

    def _create_target(self, amount):
        return self.env["sng.commission.target"].create(
            {
                "plan_id": self.plan.id,
                "salesperson_id": self.salesperson.id,
                "year": self.test_year,
                "month": self.test_month_str,
                "target_amount": amount,
            }
        )

    def _create_settlement(self):
        return self.env["sng.commission.settlement"].create(
            {
                "plan_id": self.plan.id,
                "salesperson_id": self.salesperson.id,
                "year": self.test_year,
                "month": self.test_month_str,
            }
        )

    def test_plan_overlap_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env["sng.commission.plan"].create(
                {
                    "name": "Plan traslapado",
                    "company_id": self.company.id,
                    "date_start": date(self.test_year, 6, 1),
                    "date_end": date(self.test_year, 12, 31),
                    "state": "active",
                }
            )

    def test_open_ended_plan_covers_future_periods(self):
        settlement = self.env["sng.commission.settlement"].create(
            {
                "plan_id": self.plan.id,
                "salesperson_id": self.salesperson.id,
                "year": self.test_year + 1,
                "month": "1",
            }
        )

        self.assertEqual(settlement.date_from, date(self.test_year + 1, 1, 1))
        self.assertFalse(self.plan.date_end)

    def test_activating_new_plan_closes_previous_open_ended_plan(self):
        new_start = date(self.test_year + 1, 1, 1)
        new_plan = self.env["sng.commission.plan"].create(
            {
                "name": "Plan nuevo",
                "company_id": self.company.id,
                "date_start": new_start,
                "aging_rule_ids": [
                    Command.create({"sequence": 1, "name": "No vencido", "bucket_type": "not_due", "commission_percentage": 2.0}),
                    Command.create({"sequence": 2, "name": "1-999 días", "bucket_type": "overdue", "days_from": 1, "days_to": 999, "commission_percentage": 1.0}),
                ],
                "performance_rule_ids": [
                    Command.create({"sequence": 1, "name": "0-999", "percentage_from": 0.0, "percentage_to": 999.0, "payout_factor": 100.0}),
                ],
            }
        )

        new_plan.action_activate()

        self.assertEqual(self.plan.date_end, date(self.test_year, 12, 31))
        self.assertEqual(new_plan.state, "active")
        self.assertFalse(new_plan.date_end)

    def test_plan_requires_not_due_bucket_to_activate(self):
        plan = self.env["sng.commission.plan"].create(
            {
                "name": "Plan incompleto",
                "company_id": self.company.id,
                "date_start": date(self.test_year, 1, 1),
                "date_end": date(self.test_year, 12, 31),
                "aging_rule_ids": [
                    Command.create(
                        {
                            "sequence": 1,
                            "name": "1-30 días",
                            "bucket_type": "overdue",
                            "days_from": 1,
                            "days_to": 30,
                            "commission_percentage": 1.0,
                        }
                    ),
                ],
                "performance_rule_ids": [
                    Command.create(
                        {
                            "sequence": 1,
                            "name": "0-100",
                            "percentage_from": 0.0,
                            "percentage_to": 100.0,
                            "payout_factor": 100.0,
                        }
                    ),
                ],
            }
        )

        with self.assertRaises(ValidationError):
            plan.action_activate()

    def test_settlement_generates_lines_for_partial_payments_and_inherits_salesperson(self):
        invoice = self._create_invoice(100.0, self._make_date(1), self._make_date(10))
        self.assertEqual(invoice.salesperson_id, self.salesperson)
        self._register_payment(invoice, 40.0, self._make_date(8))
        self._register_payment(invoice, 60.0, self._make_date(25))
        self._create_target(100.0)

        settlement = self._create_settlement()
        settlement.action_generate_settlement()

        self.assertEqual(settlement.line_count, 2)
        self.assertEqual(settlement.performance_factor, 100.0)
        self.assertEqual(settlement.actual_sales_amount, 100.0)
        self.assertAlmostEqual(
            settlement.total_amount_applied_company,
            sum(settlement.line_ids.mapped("amount_applied_company")),
            places=2,
        )
        self.assertSetEqual(set(settlement.line_ids.mapped("aging_bucket_label")), {"No vencido", "1-45 días"})
        self.assertTrue(all(line.salesperson_id == self.salesperson for line in settlement.line_ids))

    def test_settlement_applies_performance_factor(self):
        invoice = self._create_invoice(100.0, self._make_date(1), self._make_date(10))
        self._register_payment(invoice, 100.0, self._make_date(15))
        self._create_target(90.0)

        settlement = self._create_settlement()
        settlement.action_generate_settlement()

        self.assertAlmostEqual(settlement.achievement_percentage, 111.1111111111, places=2)
        self.assertEqual(settlement.performance_factor, 115.0)
        self.assertTrue(settlement.adjusted_commission_amount > settlement.gross_commission_amount)

    def test_actual_sales_uses_invoice_report_salesperson_rule(self):
        report_salesperson = self.env["res.partner"].create(
            {
                "name": "Vendedor reporte comisión",
                "is_salesperson": True,
            }
        )
        invoice_user = new_test_user(
            self.env,
            login="sng-commission-report-rule-user",
            groups="account.group_account_invoice",
            company_id=self.company.id,
            name="Usuario regla reporte comisión",
        )
        self.env["invoice.report.salesperson.rule"].create(
            {
                "company_id": self.company.id,
                "user_id": invoice_user.id,
                "salesperson_id": report_salesperson.id,
            }
        )
        self._create_invoice(
            100.0,
            self._make_date(1),
            self._make_date(10),
            invoice_user=invoice_user,
        )

        original_settlement = self._create_settlement()
        report_settlement = self.env["sng.commission.settlement"].create(
            {
                "plan_id": self.plan.id,
                "salesperson_id": report_salesperson.id,
                "year": self.test_year,
                "month": self.test_month_str,
            }
        )

        self.assertEqual(original_settlement._get_actual_sales_amount(), 0.0)
        self.assertEqual(report_settlement._get_actual_sales_amount(), 100.0)

    def test_payment_report_groups_lines_by_payment_and_currency(self):
        invoice_a = self._create_invoice(100.0, self._make_date(1), self._make_date(20))
        invoice_b = self._create_invoice(200.0, self._make_date(2), self._make_date(20))
        self._register_payment_for_invoices(invoice_a | invoice_b, 300.0, self._make_date(8))
        self._create_target(300.0)

        settlement = self._create_settlement()
        settlement.action_generate_settlement()
        self.assertEqual(len(settlement.line_ids), 2)
        first_line = settlement.line_ids[:1]
        settlement.line_ids.write(
            {
                "payment_id": first_line.payment_id.id,
                "payment_move_id": first_line.payment_move_id.id,
                "source_currency_id": first_line.source_currency_id.id,
            }
        )
        data = settlement._get_payment_report_data()

        self.assertEqual(len(data["summaries"]), 1)
        self.assertEqual(data["summaries"][0]["invoice_count"], 2)
        self.assertEqual(len(data["details"]), 2)
        self.assertAlmostEqual(
            data["summaries"][0]["final_commission_amount"],
            sum(settlement.line_ids.mapped("final_commission_amount")),
            places=2,
        )
        self.assertEqual(
            data["details"][0]["invoice"],
            settlement.line_ids.sorted(lambda line: (line.applied_date, line.invoice_id.name, line.id))[0].invoice_id,
        )

    def test_payment_report_actions_return_pdf_and_excel_download(self):
        invoice = self._create_invoice(100.0, self._make_date(1), self._make_date(20))
        self._register_payment(invoice, 100.0, self._make_date(8))
        self._create_target(100.0)

        settlement = self._create_settlement()
        settlement.action_generate_settlement()

        pdf_action = settlement.action_print_payment_report_pdf()
        self.assertEqual(pdf_action["type"], "ir.actions.report")
        self.assertEqual(pdf_action["report_name"], "sng_sales_commission.report_commission_payment_detail")

        excel_action = settlement.action_export_payment_report_xlsx()
        self.assertEqual(excel_action["type"], "ir.actions.act_url")
        self.assertIn("/web/content/", excel_action["url"])
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", settlement._name),
                ("res_id", "=", settlement.id),
                ("name", "ilike", "reporte_pagos_comision_"),
            ],
            limit=1,
        )
        self.assertTrue(attachment)
        self.assertEqual(
            attachment.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_reversed_invoice_is_excluded_from_actual_sales_and_commissions(self):
        invoice = self._create_invoice(100.0, self._make_date(1), self._make_date(10))
        self._register_payment(invoice, 100.0, self._make_date(8))
        self._reverse_invoice(invoice)
        self.assertEqual(invoice.payment_state, "reversed")
        self._create_target(100.0)

        settlement = self._create_settlement()
        settlement.action_generate_settlement()

        self.assertEqual(settlement.actual_sales_amount, 0.0)
        self.assertEqual(settlement.achievement_percentage, 0.0)
        self.assertEqual(settlement.line_count, 0)

    def test_multi_currency_payment_keeps_source_currency_and_company_amount(self):
        if not self.foreign_currency:
            raise SkipTest("No hay moneda secundaria activa para validar conversión.")

        invoice = self._create_invoice(100.0, self._make_date(1), self._make_date(10), currency=self.foreign_currency)
        self._register_payment(invoice, 100.0, self._make_date(15))
        self._create_target(abs(invoice.amount_untaxed_signed))

        settlement = self._create_settlement()
        settlement.action_generate_settlement()

        line = settlement.line_ids[:1]
        self.assertEqual(line.source_currency_id, self.foreign_currency)
        self.assertTrue(line.amount_applied_company > 0.0)
        self.assertNotEqual(line.amount_applied_company, line.amount_applied_untaxed_source)

    def test_recalculation_is_blocked_when_settlement_is_approved(self):
        settlement = self._create_settlement()
        settlement.action_approve()
        with self.assertRaises(UserError):
            settlement.action_generate_settlement()

    def test_settlement_explains_missing_not_due_bucket(self):
        plan = self.env["sng.commission.plan"].create(
            {
                "name": "Plan legado incompleto",
                "company_id": self.company.id,
                "date_start": date(self.test_year, 1, 1),
                "date_end": date(self.test_year, 12, 31),
                "aging_rule_ids": [
                    Command.create(
                        {
                            "sequence": 1,
                            "name": "1-45 días",
                            "bucket_type": "overdue",
                            "days_from": 1,
                            "days_to": 45,
                            "commission_percentage": 1.5,
                        }
                    ),
                ],
                "performance_rule_ids": [
                    Command.create(
                        {
                            "sequence": 1,
                            "name": "0-100",
                            "percentage_from": 0.0,
                            "percentage_to": 100.0,
                            "payout_factor": 100.0,
                        }
                    ),
                ],
            }
        )
        invoice = self._create_invoice(100.0, self._make_date(1), self._make_date(10))
        self._register_payment(invoice, 100.0, self._make_date(8))
        self.env["sng.commission.target"].create(
            {
                "plan_id": plan.id,
                "salesperson_id": self.salesperson.id,
                "year": self.test_year,
                "month": self.test_month_str,
                "target_amount": 100.0,
            }
        )
        settlement = self.env["sng.commission.settlement"].create(
            {
                "plan_id": plan.id,
                "salesperson_id": self.salesperson.id,
                "year": self.test_year,
                "month": self.test_month_str,
            }
        )

        with self.assertRaisesRegex(UserError, "No vencido"):
            settlement.action_generate_settlement()
