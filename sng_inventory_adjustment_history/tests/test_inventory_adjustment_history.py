# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user


class TestInventoryAdjustmentHistory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse_group = cls.env["sng.warehouse.group"].create(
            {
                "name": "Almacenes con historial",
                "warehouse_ids": [(6, 0, cls.warehouse.ids)],
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Producto con historial de ajuste",
                "is_storable": True,
                "standard_price": 4.0,
            }
        )
        cls.stock_user_without_cost = new_test_user(
            cls.env,
            login="inventory_history_without_cost",
            groups="stock.group_stock_user",
            company_id=cls.env.company.id,
        )

    def test_adjustment_in_grouped_warehouse_creates_history(self):
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "inventory_quantity": 10.0,
            }
        )

        quant.action_apply_inventory()

        history = self.env["sng.inventory.adjustment.history"].search(
            [("quant_id", "=", quant.id)]
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history.warehouse_id, self.warehouse)
        self.assertIn(self.warehouse_group, history.warehouse_group_ids)
        self.assertEqual(history.product_id, self.product)
        self.assertEqual(history.adjusted_by_id, self.env.user)
        self.assertAlmostEqual(history.previous_quantity, 0.0)
        self.assertAlmostEqual(history.adjusted_quantity, 10.0)
        self.assertAlmostEqual(history.new_quantity, 10.0)
        self.assertAlmostEqual(history.unit_cost, 4.0)
        self.assertAlmostEqual(history.adjustment_cost, 40.0)
        self.assertTrue(history.move_ids)

        quant.inventory_quantity = 7.0
        quant.action_apply_inventory()
        reduction_history = self.env["sng.inventory.adjustment.history"].search(
            [("quant_id", "=", quant.id), ("id", "!=", history.id)]
        )
        self.assertEqual(len(reduction_history), 1)
        self.assertAlmostEqual(reduction_history.previous_quantity, 10.0)
        self.assertAlmostEqual(reduction_history.adjusted_quantity, -3.0)
        self.assertAlmostEqual(reduction_history.new_quantity, 7.0)
        self.assertAlmostEqual(reduction_history.unit_cost, 4.0)
        self.assertAlmostEqual(reduction_history.adjustment_cost, -12.0)

    def test_cost_fields_follow_custom_ui_security_group(self):
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "inventory_quantity": 2.0,
            }
        )
        quant.action_apply_inventory()
        history = self.env["sng.inventory.adjustment.history"].search(
            [("quant_id", "=", quant.id)]
        )

        public_values = history.with_user(self.stock_user_without_cost).read(
            ["previous_quantity", "adjusted_quantity", "new_quantity"]
        )
        self.assertEqual(public_values[0]["new_quantity"], 2.0)
        with self.assertRaises(AccessError):
            history.with_user(self.stock_user_without_cost).read(["unit_cost"])
        with self.assertRaises(AccessError):
            history.with_user(self.stock_user_without_cost).read(
                ["adjustment_cost"]
            )

    def test_adjustment_sends_notification_email(self):
        self.warehouse_group.adjustment_notify_emails = (
            "bodega@example.com, auditoria@example.com"
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "inventory_quantity": 5.0,
            }
        )

        quant.action_apply_inventory()

        mail = self.env["mail.mail"].search(
            [("email_to", "=", "bodega@example.com, auditoria@example.com")]
        )
        self.assertEqual(len(mail), 1)
        self.assertIn(self.warehouse_group.name, mail.subject)
        self.assertIn(self.product.display_name, mail.body_html)
        self.assertEqual(mail.state, "outgoing")

    def test_adjustment_without_notify_emails_sends_nothing(self):
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.warehouse.lot_stock_id.id,
                "inventory_quantity": 4.0,
            }
        )
        mails_before = self.env["mail.mail"].search_count([])

        quant.action_apply_inventory()

        self.assertEqual(self.env["mail.mail"].search_count([]), mails_before)

    def test_adjustment_outside_grouped_warehouse_is_ignored(self):
        location = self.env["stock.location"].create(
            {
                "name": "Ubicación sin almacén agrupado",
                "usage": "internal",
                "company_id": self.env.company.id,
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": location.id,
                "inventory_quantity": 3.0,
            }
        )

        quant.action_apply_inventory()

        history = self.env["sng.inventory.adjustment.history"].search(
            [("quant_id", "=", quant.id)]
        )
        self.assertFalse(history)
