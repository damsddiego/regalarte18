# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import Form, TransactionCase, new_test_user


class TestAdjustmentApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1,
        )
        cls.group = cls.env["sng.warehouse.group"].create({
            "name": "Aprobaciones de prueba",
            "warehouse_ids": [(6, 0, cls.warehouse.ids)],
            "adjustment_approval_emails": "gerencia-approval@example.com",
            "adjustment_sender_email": "notificaciones@example.com",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Producto de prueba de aprobación", "is_storable": True,
            "standard_price": 10.0,
        })
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 10.0,
        )
        cls.quant = cls.env["stock.quant"].search([
            ("product_id", "=", cls.product.id),
            ("location_id", "=", cls.warehouse.lot_stock_id.id),
        ], limit=1)
        cls.operator = new_test_user(
            cls.env, login="adjustment.operator", groups="stock.group_stock_user",
            company_id=cls.company.id,
        )
        cls.stock_manager = new_test_user(
            cls.env, login="adjustment.stock.manager", groups="stock.group_stock_manager",
            company_id=cls.company.id,
        )
        cls.approver = new_test_user(
            cls.env, login="adjustment.approver",
            groups="sng_inventory_adjustment_history.group_inventory_adjustment_approver",
            company_id=cls.company.id,
        )

    def _request(self, user=None, quantity=8.0):
        return self.env["sng.inventory.adjustment.request"].with_user(user or self.operator).create({
            "quant_id": self.quant.id, "counted_quantity": quantity,
            "reason": "Diferencia comprobada en conteo físico.",
        })

    def test_draft_and_submit_only_send_request_without_adjusting_stock(self):
        request = self._request()
        self.assertEqual(request.state, "draft")
        self.assertEqual(request.previous_quantity, 10.0)
        self.assertEqual(request.difference_quantity, -2.0)
        self.assertEqual(request.requested_by_id, self.operator)
        with self.assertRaises(AccessError):
            request.read(["unit_cost"])
        request.action_submit()
        self.assertEqual(request.state, "pending")
        self.assertEqual(self.quant.quantity, 10.0)
        self.assertFalse(request.move_ids)
        self.assertFalse(request.history_ids)
        mail = self.env["mail.mail"].search([
            ("model", "=", request._name), ("res_id", "=", request.id),
        ])
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.email_to, "gerencia-approval@example.com")
        self.assertEqual(mail.email_from, "notificaciones@example.com")
        self.assertEqual(mail.state, "outgoing")
        self.assertIn(request.reason, mail.body_html)
        self.assertIn("model=sng.inventory.adjustment.request", mail.body_html)
        self.assertIn("Costo estimado", mail.body_html)

    def test_only_approver_can_apply_and_repeated_approval_is_blocked(self):
        request = self._request()
        request.action_submit()
        for user in (self.operator, self.stock_manager):
            with self.assertRaises(AccessError):
                request.with_user(user).action_approve()
        request.with_user(self.approver).action_approve()
        self.assertEqual(self.quant.quantity, 8.0)
        self.assertEqual(request.state, "approved")
        self.assertEqual(request.reviewed_by_id, self.approver)
        self.assertTrue(request.move_ids)
        history = request.history_ids
        self.assertEqual(len(history), 1)
        self.assertEqual(history.counted_by_id, self.operator)
        self.assertEqual(history.adjusted_by_id, self.approver)
        self.assertEqual(history.reason, request.reason)
        with self.assertRaises(UserError):
            request.with_user(self.approver).action_approve()
        self.assertEqual(self.quant.quantity, 8.0)

    def test_approver_cannot_approve_own_request(self):
        request = self._request(user=self.approver, quantity=12.0)
        request.action_submit()
        with self.assertRaises(AccessError):
            request.action_approve()
        self.assertEqual(self.quant.quantity, 10.0)

    def test_native_capture_cannot_be_self_applied_or_reassigned_to_hide_actor(self):
        quant = self.quant.with_user(self.approver)
        quant.write({"inventory_quantity": 8})
        quant.write({"user_id": self.operator.id})
        with self.assertRaises(AccessError):
            quant.action_apply_inventory()
        with self.assertRaises(AccessError):
            quant.write({"sng_counted_by_ids": [(5, 0, 0)]})
        with self.assertRaises(UserError):
            quant.write({"inventory_quantity_auto_apply": 8})
        request = self._request(user=self.operator)
        request.action_submit()
        with self.assertRaises(AccessError):
            request.with_user(self.approver).action_approve()

    def test_independent_manager_can_apply_native_count(self):
        self.quant.with_user(self.operator).write({"inventory_quantity": 8})
        self.quant.with_user(self.approver).action_apply_inventory()
        self.assertEqual(self.quant.quantity, 8)
        self.assertFalse(self.quant.sng_counted_by_ids)

    def test_submitting_native_capture_preserves_actual_counter(self):
        self.quant.with_user(self.operator).write({"inventory_quantity": 8, "sng_adjustment_reason": "Conteo físico"})
        action = self.quant.with_user(self.approver).action_request_inventory_approval()
        request = self.env["sng.inventory.adjustment.request"].search(action["domain"])
        self.assertEqual(request.counted_by_ids, self.operator)
        self.assertEqual(request.requested_by_id, self.approver)
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.history_ids.counted_by_id, self.operator)

    def test_inventory_difference_cannot_be_forged(self):
        self.quant.with_user(self.operator).write({"inventory_quantity": 8})
        with self.assertRaises(AccessError):
            self.quant.with_user(self.operator).write({"inventory_diff_quantity": -9})
        self.assertEqual(self.quant.inventory_diff_quantity, -2)

    def test_native_count_remains_pending_and_direct_routes_are_denied(self):
        quant = self.quant.with_user(self.operator).with_context(inventory_mode=True)
        quant.write({"inventory_quantity": 8, "sng_adjustment_reason": "Producto dañado."})
        self.assertEqual(quant.quantity, 10.0)
        self.assertTrue(quant.inventory_quantity_set)
        for method in ("action_apply_inventory", "action_apply_all", "_apply_inventory"):
            with self.assertRaises(AccessError):
                getattr(quant, method)()
        for vals in ({"inventory_quantity_auto_apply": 8}, {"quantity": 8}):
            with self.assertRaises(AccessError):
                quant.write(vals)
            with self.assertRaises(AccessError):
                self.env["stock.quant"].with_user(self.operator).with_context(inventory_mode=True).create({
                    "product_id": self.product.id,
                    "location_id": self.warehouse.lot_stock_id.id,
                    **vals,
                })
        action = quant.action_request_inventory_approval()
        self.assertEqual(action["res_model"], "sng.inventory.adjustment.request")
        self.assertEqual(quant.quantity, 10.0)

    def test_native_wizards_cannot_bypass_permission(self):
        self.quant.inventory_quantity = 8
        wizard = self.env["stock.inventory.adjustment.name"].with_user(self.operator).create({
            "quant_ids": [(6, 0, self.quant.ids)],
        })
        with self.assertRaises(AccessError):
            wizard.action_apply()
        tracking = self.env["stock.track.confirmation"].with_user(self.operator).create({
            "quant_ids": [(6, 0, self.quant.ids)],
        })
        with self.assertRaises(AccessError):
            tracking.action_confirm()

    def test_pending_snapshot_cannot_be_modified_or_bypassed(self):
        request = self._request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.write({"counted_quantity": 9})
        with self.assertRaises(AccessError):
            request.write({"state": "approved"})
        with self.assertRaises(AccessError):
            request.write({"previous_quantity": 9})
        with self.assertRaises(UserError):
            self.quant.with_user(self.operator).write({"inventory_quantity": 9})
        with self.assertRaises(UserError):
            self.quant.with_user(self.approver)._apply_inventory()
        duplicate = self._request()
        with self.assertRaises(UserError):
            duplicate.action_submit()

    def test_changed_stock_requires_new_count(self):
        request = self._request()
        request.action_submit()
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 1.0,
        )
        with self.assertRaises(UserError):
            request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "pending")
        self.assertEqual(self.quant.quantity, 11.0)

    def test_reason_required_and_rejection_does_not_change_stock(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["sng.inventory.adjustment.request"].with_user(self.operator).create({
                "quant_id": self.quant.id, "counted_quantity": 8, "reason": "   ",
            })
        request = self._request()
        request.action_submit()
        with self.assertRaises(AccessError):
            request.action_reject()
        request = request.with_user(self.approver)
        with self.assertRaises(UserError):
            request.action_reject()
        request.review_note = "Repetir el conteo con supervisión."
        request.action_reject()
        self.assertEqual(request.state, "rejected")
        self.assertEqual(self.quant.quantity, 10.0)

    def test_stock_manager_without_approval_group_cannot_apply(self):
        self.quant.inventory_quantity = 8
        with self.assertRaises(AccessError):
            self.quant.with_user(self.stock_manager).action_apply_inventory()

    def test_approved_backend_flows_and_regular_stock_updates_still_work(self):
        # Cycle-count management calls this private sudo path after its own approval.
        quant = self.quant.with_user(self.stock_manager).sudo().with_context(inventory_mode=True)
        quant.inventory_quantity = 9
        quant._apply_inventory()
        self.assertEqual(quant.quantity, 9.0)
        self.env["stock.quant"].with_user(self.operator)._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 1.0,
        )
        self.assertEqual(quant.quantity, 10.0)

    def test_quant_cleanup_preserves_request_reference(self):
        request = self._request()
        self.quant.sudo().unlink()
        self.assertTrue(request.quant_id.exists())

    def test_operator_can_save_draft_from_form(self):
        with Form(self.env["sng.inventory.adjustment.request"].with_user(self.operator)) as form:
            form.quant_id = self.quant
            form.counted_quantity = 8
            form.reason = "Reconteo físico con diferencia."
        self.assertEqual(form.record.state, "draft")
        self.assertEqual(form.record.previous_quantity, 10)
        self.assertEqual(self.quant.quantity, 10)

    def test_native_create_keeps_reason_and_cannot_overwrite_pending(self):
        model = self.env["stock.quant"].with_user(self.operator).with_context(inventory_mode=True)
        vals = {
            "product_id": self.product.id, "location_id": self.warehouse.lot_stock_id.id,
            "inventory_quantity": 8, "sng_adjustment_reason": "Diferencia confirmada.",
        }
        quant = model.create(vals).with_user(self.operator)
        self.assertEqual(quant, self.quant)
        self.assertEqual(quant.sng_adjustment_reason, "Diferencia confirmada.")
        quant.action_request_inventory_approval()
        with self.assertRaises(UserError):
            model.create(vals)

    def test_operators_cannot_read_others_requests(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.with_user(self.stock_manager).read(["reason"])
        self.assertEqual(request.with_user(self.approver).read(["reason"])[0]["reason"], request.reason)

    def test_missing_recipients_keeps_draft(self):
        self.group.write({"adjustment_approval_emails": False})
        self.approver.email = False
        request = self._request()
        with self.assertRaises(UserError), self.cr.savepoint():
            request.action_submit()
        self.assertEqual(request.state, "draft")
        self.assertEqual(self.quant.quantity, 10)
