# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestRegalia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.expense_account = cls.env["account.account"].create({
            "code": "699999",
            "name": "Gasto regalías test",
            "account_type": "expense",
        })
        cls.counterpart_account = cls.env["account.account"].create({
            "code": "119999",
            "name": "Inventario regalías test",
            "account_type": "asset_current",
        })
        cls.journal = cls.env["account.journal"].search([
            ("company_id", "=", cls.company.id),
            ("type", "=", "general"),
        ], limit=1)
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create({
                "name": "Misceláneo regalías test",
                "code": "RGT",
                "type": "general",
            })
        cls.company.write({
            "regalia_expense_account_id": cls.expense_account.id,
            "regalia_counterpart_account_id": cls.counterpart_account.id,
            "regalia_journal_id": cls.journal.id,
        })

        cls.partner = cls.env["res.partner"].create({"name": "Cliente Regalía Test"})
        cls.product_a = cls.env["product.product"].create({
            "name": "Peluche Test A",
            "is_storable": True,
            "standard_price": 100.0,
        })
        cls.product_b = cls.env["product.product"].create({
            "name": "Peluche Test B",
            "is_storable": True,
            "standard_price": 250.0,
        })
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product_a, cls.warehouse.lot_stock_id, 10.0
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product_b, cls.warehouse.lot_stock_id, 10.0
        )

        cls.manager_user = cls.env["res.users"].create({
            "name": "Responsable Regalías",
            "login": "regalia_manager_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sng_entrega_regalias.group_regalia_manager").id,
                cls.env.ref("stock.group_stock_user").id,
                cls.env.ref("account.group_account_manager").id,
            ])],
        })
        cls.basic_user = cls.env["res.users"].create({
            "name": "Usuario Regalías",
            "login": "regalia_user_test",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("sng_entrega_regalias.group_regalia_user").id,
                cls.env.ref("stock.group_stock_user").id,
            ])],
        })

    def _create_regalia(self, lines=None):
        if lines is None:
            lines = [
                (self.product_a, 2.0),
                (self.product_b, 3.0),
            ]
        return self.env["sng.regalia"].create({
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
            "date": fields.Date.today(),
            "line_ids": [
                (0, 0, {"product_id": product.id, "quantity": qty})
                for product, qty in lines
            ],
        })

    def test_validate_creates_picking_and_move(self):
        regalia = self._create_regalia()
        self.assertNotEqual(regalia.name, "New")

        regalia.with_user(self.manager_user).action_validate()

        self.assertEqual(regalia.state, "done")
        self.assertEqual(regalia.picking_id.state, "done")
        self.assertEqual(regalia.picking_id.partner_id, self.partner)
        self.assertEqual(regalia.picking_id.origin, regalia.name)
        self.assertEqual(
            self.product_a.with_context(
                location=self.warehouse.lot_stock_id.id
            ).qty_available,
            8.0,
        )
        self.assertEqual(
            self.product_b.with_context(
                location=self.warehouse.lot_stock_id.id
            ).qty_available,
            7.0,
        )

        move = regalia.move_id
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.ref, regalia.name)
        self.assertEqual(move.journal_id, self.journal)
        expected_total = 2.0 * 100.0 + 3.0 * 250.0
        debit_lines = move.line_ids.filtered(lambda l: l.debit > 0.0)
        credit_lines = move.line_ids.filtered(lambda l: l.credit > 0.0)
        self.assertEqual(len(debit_lines), 2)
        self.assertEqual(len(credit_lines), 1)
        self.assertEqual(debit_lines.mapped("account_id"), self.expense_account)
        self.assertEqual(credit_lines.account_id, self.counterpart_account)
        self.assertEqual(sum(debit_lines.mapped("debit")), expected_total)
        self.assertEqual(credit_lines.credit, expected_total)
        self.assertFalse(move.line_ids.mapped("tax_ids"))
        self.assertEqual(regalia.amount_total, expected_total)

    def test_missing_config_raises(self):
        self.company.write({
            "regalia_expense_account_id": False,
            "regalia_counterpart_account_id": False,
        })
        regalia = self._create_regalia()
        with self.assertRaises(UserError):
            regalia.with_user(self.manager_user).action_validate()

    def test_user_cannot_validate(self):
        regalia = self._create_regalia()
        with self.assertRaises(UserError):
            regalia.with_user(self.basic_user).action_validate()

    def test_locked_after_done(self):
        regalia = self._create_regalia()
        regalia.with_user(self.manager_user).action_validate()
        with self.assertRaises(UserError):
            regalia.write({"notes": "cambio"})
        with self.assertRaises(UserError):
            regalia.line_ids[0].write({"quantity": 99.0})
        with self.assertRaises(UserError):
            regalia.unlink()

    def test_no_lines_raises(self):
        regalia = self.env["sng.regalia"].create({
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
        })
        with self.assertRaises(UserError):
            regalia.with_user(self.manager_user).action_validate()

    def test_zero_quantity_raises(self):
        with self.assertRaises(ValidationError):
            self._create_regalia(lines=[(self.product_a, 0.0)])

    def test_cancel_and_reset(self):
        regalia = self._create_regalia()
        regalia.action_cancel()
        self.assertEqual(regalia.state, "cancel")
        regalia.action_draft()
        self.assertEqual(regalia.state, "draft")

    def test_report_values(self):
        regalia = self._create_regalia()
        values = regalia._get_regalia_report_values()
        self.assertEqual(len(values["lines"]), 2)
        self.assertEqual(values["lines"][0]["quantity"], "2")
        self.assertEqual(values["totals"]["quantity"], "5")
