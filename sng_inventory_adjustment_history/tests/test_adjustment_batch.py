# -*- coding: utf-8 -*-

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAdjustmentBatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1,
        )
        cls.location = cls.warehouse.lot_stock_id
        cls.other_warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company.id), ("id", "!=", cls.warehouse.id),
        ], limit=1) or cls.env["stock.warehouse"].create({
            "name": "Bodega secundaria de prueba", "code": "BSP",
        })
        cls.env["sng.warehouse.group"].search([]).write({
            "adjustment_approval_emails": False, "adjustment_notify_emails": False,
        })
        cls.group = cls.env["sng.warehouse.group"].create({
            "name": "Aprobaciones por lote",
            "warehouse_ids": [(6, 0, cls.warehouse.ids)],
            "adjustment_approval_emails": "gerencia-lote@example.com",
            "adjustment_sender_email": "notificaciones@example.com",
        })
        cls.product_a = cls.env["product.product"].create({
            "name": "Producto A del lote", "is_storable": True, "standard_price": 10.0,
        })
        cls.product_b = cls.env["product.product"].create({
            "name": "Producto B del lote", "is_storable": True, "standard_price": 5.0,
        })
        cls.product_new = cls.env["product.product"].create({
            "name": "Producto sin existencia", "is_storable": True, "standard_price": 7.0,
        })
        cls.product_consu = cls.env["product.product"].create({
            "name": "Servicio no almacenable", "type": "consu", "is_storable": False,
        })
        Quant = cls.env["stock.quant"]
        Quant._update_available_quantity(cls.product_a, cls.location, 10.0)
        Quant._update_available_quantity(cls.product_b, cls.location, 20.0)
        Quant._update_available_quantity(cls.product_a, cls.other_warehouse.lot_stock_id, 3.0)
        cls.quant_a = Quant.search([
            ("product_id", "=", cls.product_a.id), ("location_id", "=", cls.location.id),
        ], limit=1)
        cls.quant_b = Quant.search([
            ("product_id", "=", cls.product_b.id), ("location_id", "=", cls.location.id),
        ], limit=1)
        cls.quant_a_other = Quant.search([
            ("product_id", "=", cls.product_a.id),
            ("location_id", "=", cls.other_warehouse.lot_stock_id.id),
        ], limit=1)
        cls.operator = new_test_user(
            cls.env, login="batch.operator", groups="stock.group_stock_user",
            company_id=cls.company.id,
        )
        cls.approver = new_test_user(
            cls.env, login="batch.approver",
            groups="sng_inventory_adjustment_history.group_inventory_adjustment_approver",
            company_id=cls.company.id,
        )

    def _batch(self, lines, user=None, location=None):
        return self.env["sng.inventory.adjustment.batch"].with_user(user or self.operator).create({
            "location_id": (location or self.location).id,
            "line_ids": [Command.create(vals) for vals in lines],
        })

    def test_batch_with_two_lines_resolves_quants_and_sends_one_mail(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        self.assertEqual(batch.state, "draft")
        self.assertEqual(batch.warehouse_id, self.warehouse)
        self.assertEqual(batch.requested_by_id, self.operator)
        line_a, line_b = batch.line_ids.sorted("id")
        self.assertEqual(line_a.quant_id, self.quant_a)
        self.assertEqual(line_b.quant_id, self.quant_b)
        self.assertEqual(line_a.previous_quantity, 10)
        self.assertEqual(line_b.previous_quantity, 20)
        self.assertEqual(line_a.difference_quantity, -2)
        self.assertEqual(line_b.difference_quantity, 2)
        batch.action_submit()
        self.assertEqual(batch.state, "pending")
        self.assertEqual(set(batch.line_ids.mapped("state")), {"pending"})
        self.assertEqual(self.quant_a.quantity, 10)
        self.assertEqual(self.quant_b.quantity, 20)
        mails = self.env["mail.mail"].search([
            ("model", "=", batch._name), ("res_id", "=", batch.id),
        ])
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.email_to, "gerencia-lote@example.com")
        self.assertEqual(mails.email_from, "notificaciones@example.com")
        self.assertIn(self.product_a.display_name, mails.body_html)
        self.assertIn(self.product_b.display_name, mails.body_html)
        self.assertIn("Faltante A", mails.body_html)
        self.assertIn("model=sng.inventory.adjustment.batch", mails.body_html)

    def test_approving_batch_applies_every_line(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.action_submit()
        with self.assertRaises(AccessError):
            batch.action_approve()
        batch.with_user(self.approver).action_approve()
        self.assertEqual(batch.state, "approved")
        self.assertEqual(batch.reviewed_by_id, self.approver)
        self.assertEqual(self.quant_a.quantity, 8)
        self.assertEqual(self.quant_b.quantity, 22)
        self.assertEqual(len(batch.history_ids), 2)
        self.assertEqual(batch.history_ids.mapped("batch_id"), batch)
        self.assertEqual(set(batch.line_ids.mapped("state")), {"approved"})
        with self.assertRaises(UserError):
            batch.with_user(self.approver).action_approve()

    def test_product_without_stock_in_location_gets_zero_quant(self):
        self.assertFalse(self.env["stock.quant"].search([
            ("product_id", "=", self.product_new.id), ("location_id", "=", self.location.id),
        ]))
        batch = self._batch([
            {"product_id": self.product_new.id, "counted_quantity": 3, "reason": "Encontrado en estante"},
        ])
        line = batch.line_ids
        self.assertTrue(line.quant_id)
        self.assertEqual(line.quant_id.location_id, self.location)
        self.assertEqual(line.previous_quantity, 0)
        self.assertEqual(line.difference_quantity, 3)
        self.assertEqual(line.quant_id.quantity, 0)
        # La limpieza de existencias en cero no debe borrar la referencia.
        self.env["stock.quant"]._unlink_zero_quants()
        self.assertTrue(line.quant_id.exists())
        batch.action_submit()
        batch.with_user(self.approver).action_approve()
        self.assertEqual(line.quant_id.quantity, 3)
        self.assertEqual(self.product_new.with_context(location=self.location.id).qty_available, 3)

    def test_non_storable_product_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._batch([
                {"product_id": self.product_consu.id, "counted_quantity": 1, "reason": "No aplica"},
            ])

    def test_line_must_belong_to_batch_location(self):
        with self.assertRaises(ValidationError):
            self._batch([
                {"quant_id": self.quant_a_other.id, "counted_quantity": 1, "reason": "Otra bodega"},
            ])
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
        ])
        with self.assertRaises(UserError):
            batch.write({"location_id": self.other_warehouse.lot_stock_id.id})

    def test_same_product_twice_in_a_batch_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._batch([
                {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Uno"},
                {"product_id": self.product_a.id, "counted_quantity": 9, "reason": "Dos"},
            ])

    def test_changing_product_in_draft_line_resolves_new_quant(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante"},
        ])
        line = batch.line_ids
        line.write({"product_id": self.product_b.id})
        self.assertEqual(line.quant_id, self.quant_b)
        self.assertEqual(line.previous_quantity, 20)
        batch.action_submit()
        with self.assertRaises(UserError):
            line.write({"product_id": self.product_a.id})

    def test_partial_reject_then_approve_rest(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.action_submit()
        line_a, line_b = batch.line_ids.sorted("id")
        line_b = line_b.with_user(self.approver)
        line_b.review_note = "Recontar B con supervisión."
        line_b.action_reject()
        self.assertEqual(line_b.state, "rejected")
        self.assertEqual(batch.state, "pending")
        batch.with_user(self.approver).action_approve()
        self.assertEqual(batch.state, "approved")
        self.assertEqual(line_a.state, "approved")
        self.assertEqual(self.quant_a.quantity, 8)
        self.assertEqual(self.quant_b.quantity, 20)

    def test_reject_batch_requires_note_and_keeps_stock(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.action_submit()
        approver_batch = batch.with_user(self.approver)
        with self.assertRaises(UserError):
            approver_batch.action_reject()
        approver_batch.review_note = "Repetir el conteo completo."
        approver_batch.action_reject()
        self.assertEqual(batch.state, "rejected")
        self.assertEqual(set(batch.line_ids.mapped("state")), {"rejected"})
        self.assertEqual(batch.line_ids.mapped("review_note"), ["Repetir el conteo completo."] * 2)
        self.assertEqual(self.quant_a.quantity, 10)
        self.assertEqual(self.quant_b.quantity, 20)

    def test_lines_cannot_be_added_or_removed_after_submit(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
        ])
        batch.action_submit()
        with self.assertRaises(UserError):
            batch.write({"line_ids": [Command.create({
                "product_id": self.product_b.id, "counted_quantity": 1, "reason": "Tarde",
            })]})
        with self.assertRaises(UserError):
            batch.line_ids.unlink()
        with self.assertRaises(UserError):
            batch.unlink()

    def test_draft_batch_can_remove_lines_and_be_deleted(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.line_ids.sorted("id")[1].unlink()
        self.assertEqual(len(batch.line_ids), 1)
        batch.unlink()
        self.assertFalse(batch.exists())

    def test_submit_requires_lines(self):
        batch = self.env["sng.inventory.adjustment.batch"].with_user(self.operator).create({
            "location_id": self.location.id,
        })
        with self.assertRaises(UserError):
            batch.action_submit()

    def test_physical_inventory_request_groups_by_location(self):
        self.quant_a.with_user(self.operator).write({
            "inventory_quantity": 8, "sng_adjustment_reason": "Faltante A",
        })
        self.quant_b.with_user(self.operator).write({
            "inventory_quantity": 22, "sng_adjustment_reason": "Sobrante B",
        })
        self.quant_a_other.with_user(self.operator).write({
            "inventory_quantity": 1, "sng_adjustment_reason": "Otra bodega",
        })
        quants = self.quant_a | self.quant_b | self.quant_a_other
        action = quants.with_user(self.operator).action_request_inventory_approval()
        self.assertEqual(action["res_model"], "sng.inventory.adjustment.batch")
        batches = self.env["sng.inventory.adjustment.batch"].search(action["domain"])
        self.assertEqual(len(batches), 2)
        main = batches.filtered(lambda b: b.location_id == self.location)
        self.assertEqual(len(main.line_ids), 2)
        self.assertEqual(main.state, "pending")
        self.assertEqual(main.line_ids.mapped("reason"), ["Faltante A", "Sobrante B"])
        other = batches - main
        self.assertEqual(other.location_id, self.other_warehouse.lot_stock_id)
        self.assertEqual(other.line_ids.quant_id, self.quant_a_other)

    def test_operator_cannot_read_other_operators_batches(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
        ])
        other = new_test_user(
            self.env, login="batch.other", groups="stock.group_stock_user",
            company_id=self.company.id,
        )
        with self.assertRaises(AccessError):
            batch.with_user(other).read(["location_id"])
        self.assertEqual(
            batch.with_user(self.approver).read(["location_id"])[0]["location_id"][0],
            self.location.id,
        )

    def test_changed_stock_applies_count_difference_on_current_stock(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.action_submit()
        line_a, line_b = batch.line_ids.sorted("id")
        # Salieron 3 de B después del conteo: el faltante/sobrante detectado se conserva.
        self.env["stock.quant"]._update_available_quantity(self.product_b, self.location, -3.0)
        self.assertFalse(line_a.stock_changed)
        self.assertTrue(line_b.stock_changed)
        self.assertEqual(line_b.previous_quantity, 20)
        self.assertEqual(line_b.current_quantity, 17)
        self.assertEqual(line_b.difference_quantity, 2)
        self.assertEqual(line_b.result_quantity, 19)
        self.assertEqual(line_a.result_quantity, 8)
        batch.with_user(self.approver).action_approve()
        self.assertEqual(batch.state, "approved")
        self.assertEqual(self.quant_a.quantity, 8)
        self.assertEqual(self.quant_b.quantity, 19)
        history_b = batch.history_ids.filtered(lambda h: h.product_id == self.product_b)
        self.assertEqual(history_b.previous_quantity, 17)
        self.assertEqual(history_b.adjusted_quantity, 2)
        self.assertEqual(history_b.new_quantity, 19)

    def test_negative_result_blocks_only_until_line_is_rejected(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 4, "reason": "Faltante de 6"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.action_submit()
        line_a = batch.line_ids.sorted("id")[0]
        # Quedan 3 y el faltante detectado era 6: no se puede dejar en -3.
        self.env["stock.quant"]._update_available_quantity(self.product_a, self.location, -7.0)
        self.assertEqual(line_a.result_quantity, -3)
        with self.assertRaises(UserError):
            batch.with_user(self.approver).action_approve()
        self.assertEqual(batch.state, "pending")
        self.assertEqual(self.quant_a.quantity, 3)
        self.assertEqual(self.quant_b.quantity, 20)
        line_a = line_a.with_user(self.approver)
        line_a.review_note = "Resultado negativo, recontar."
        line_a.action_reject()
        batch.with_user(self.approver).action_approve()
        self.assertEqual(batch.state, "approved")
        self.assertEqual(self.quant_a.quantity, 3)
        self.assertEqual(self.quant_b.quantity, 22)

    def test_recalculate_refreshes_figures_and_logs_changed_lines(self):
        batch = self._batch([
            {"product_id": self.product_a.id, "counted_quantity": 8, "reason": "Faltante A"},
            {"product_id": self.product_b.id, "counted_quantity": 22, "reason": "Sobrante B"},
        ])
        batch.action_submit()
        with self.assertRaises(AccessError):
            batch.action_recalculate()
        self.env["stock.quant"]._update_available_quantity(self.product_b, self.location, -3.0)
        messages_before = len(batch.message_ids)
        batch.with_user(self.approver).action_recalculate()
        self.assertTrue(batch.recalculated_at)
        line_a, line_b = batch.line_ids.sorted("id")
        # El conteo original no se toca; solo cambian las cifras al día.
        self.assertEqual(line_b.previous_quantity, 20)
        self.assertEqual(line_b.counted_quantity, 22)
        self.assertEqual(line_b.current_quantity, 17)
        self.assertEqual(line_b.result_quantity, 19)
        self.assertEqual(len(batch.message_ids), messages_before + 1)
        body = batch.message_ids[0].body
        self.assertIn(self.product_b.display_name, body)
        self.assertNotIn(self.product_a.display_name, body)
        self.assertEqual(self.quant_b.quantity, 17)
        self.assertEqual(batch.state, "pending")
