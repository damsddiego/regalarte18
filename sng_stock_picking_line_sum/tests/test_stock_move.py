# -*- coding: utf-8 -*-

from unittest import SkipTest

from odoo import Command
from odoo.tests import TransactionCase


class TestStockMoveLineNumber(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.product = cls.env["product.product"].search(
            [("is_storable", "=", True)],
            limit=1,
        )
        if not cls.product:
            raise SkipTest("No storable product is available to test stock moves.")
        cls.picking_types = {
            "incoming": cls.env.ref("stock.picking_type_in"),
            "outgoing": cls.env.ref("stock.picking_type_out"),
            "internal": cls.env.ref("stock.picking_type_internal"),
        }

    def _create_picking(self, picking_type):
        source = picking_type.default_location_src_id
        destination = picking_type.default_location_dest_id
        move_values = {
            "name": self.product.display_name,
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "product_uom": self.product.uom_id.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
        }
        return self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "move_ids_without_package": [
                    Command.create({**move_values, "sequence": 10}),
                    Command.create({**move_values, "sequence": 20}),
                ],
            }
        )

    def test_line_number_covers_all_transfer_types(self):
        for code, picking_type in self.picking_types.items():
            with self.subTest(picking_type=code):
                picking = self._create_picking(picking_type)
                self.assertEqual(
                    picking.move_ids_without_package.mapped("line_number"),
                    [1, 2],
                )

    def test_line_number_recomputes_all_siblings_after_reorder(self):
        picking = self._create_picking(self.picking_types["internal"])
        first_move, second_move = picking.move_ids_without_package

        second_move.sequence = 5

        self.assertEqual(second_move.line_number, 1)
        self.assertEqual(first_move.line_number, 2)

    def test_line_number_recomputes_after_move_creation(self):
        picking = self._create_picking(self.picking_types["incoming"])
        first_move = picking.move_ids_without_package[0]

        new_move = self.env["stock.move"].create(
            {
                "name": self.product.display_name,
                "picking_id": picking.id,
                "sequence": 5,
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "product_uom": self.product.uom_id.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
            }
        )

        self.assertEqual(new_move.line_number, 1)
        self.assertEqual(first_move.line_number, 2)

    def test_line_number_recomputes_after_move_deletion(self):
        picking = self._create_picking(self.picking_types["outgoing"])
        first_move, second_move = picking.move_ids_without_package
        self.assertEqual(second_move.line_number, 2)

        first_move.unlink()

        self.assertEqual(second_move.line_number, 1)
