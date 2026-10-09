# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLineNotePropagation(TransactionCase):
    """La nota de la línea de venta debe llegar a la entrega, también si se
    edita después de confirmar la orden."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Notas Test"})
        cls.product = cls.env["product.product"].create({
            "name": "Producto Notas Test",
            "type": "consu",
            "is_storable": True,
            "list_price": 10.0,
        })
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
            "order_line": [(0, 0, {
                "product_id": cls.product.id,
                "product_uom_qty": 2.0,
                "sng_line_note": "NOTA INICIAL",
            })],
        })
        cls.line = cls.order.order_line

    def test_01_note_copied_on_confirm(self):
        self.order.action_confirm()
        move = self.line.move_ids
        self.assertTrue(move, "La confirmación debe crear el movimiento")
        self.assertEqual(move.sng_line_note, "NOTA INICIAL")
        if move.move_line_ids:
            self.assertEqual(set(move.move_line_ids.mapped("sng_line_note")), {"NOTA INICIAL"})

    def test_02_note_edited_after_confirm_reaches_delivery(self):
        self.order.action_confirm()
        move = self.line.move_ids
        self.line.sng_line_note = "[BODEGA] 2 de 10"
        self.assertEqual(move.sng_line_note, "[BODEGA] 2 de 10")
        for ml in move.move_line_ids:
            self.assertEqual(ml.sng_line_note, "[BODEGA] 2 de 10")

    def test_03_note_cleared_after_confirm(self):
        self.order.action_confirm()
        move = self.line.move_ids
        self.line.sng_line_note = False
        self.assertFalse(move.sng_line_note)

    def test_04_done_move_untouched(self):
        # deltatech_stock_negative bloquea salidas sin existencias
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.order.warehouse_id.lot_stock_id, 10.0
        )
        self.order.action_confirm()
        picking = self.order.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.line.sng_line_note = "CAMBIO TARDÍO"
        self.assertEqual(self.line.move_ids.sng_line_note, "NOTA INICIAL")
