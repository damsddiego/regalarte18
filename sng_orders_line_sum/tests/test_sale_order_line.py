# -*- coding: utf-8 -*-

from odoo import Command
from odoo.tests import TransactionCase


class TestSaleOrderLineNumber(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner = cls.env["res.partner"].create({"name": "Line Number Customer"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Line Number Product",
                "list_price": 10.0,
            }
        )

    def _create_order(self):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    Command.create(
                        {
                            "sequence": 10,
                            "product_id": self.product.id,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "display_type": "line_section",
                            "name": "Section",
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 30,
                            "product_id": self.product.id,
                        }
                    ),
                ],
            }
        )

    def test_line_number_skips_sections(self):
        order = self._create_order()
        first_line, section, second_line = order.order_line

        self.assertEqual(first_line.line_number, 1)
        self.assertEqual(section.line_number, 0)
        self.assertEqual(second_line.line_number, 2)

    def test_line_number_recomputes_all_siblings_after_reorder(self):
        order = self._create_order()
        first_line, section, second_line = order.order_line

        second_line.sequence = 5

        self.assertEqual(second_line.line_number, 1)
        self.assertEqual(first_line.line_number, 2)
        self.assertEqual(section.line_number, 0)

    def test_line_number_recomputes_after_line_creation(self):
        order = self._create_order()
        first_line = order.order_line[0]

        new_line = self.env["sale.order.line"].create(
            {
                "order_id": order.id,
                "sequence": 5,
                "product_id": self.product.id,
            }
        )

        self.assertEqual(new_line.line_number, 1)
        self.assertEqual(first_line.line_number, 2)

    def test_line_number_recomputes_after_line_deletion(self):
        order = self._create_order()
        first_line, section, second_line = order.order_line
        self.assertEqual(second_line.line_number, 2)

        first_line.unlink()

        self.assertEqual(section.line_number, 0)
        self.assertEqual(second_line.line_number, 1)
