# -*- coding: utf-8 -*-
from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import Form, TransactionCase, new_test_user
from lxml import etree


class TestCycleControl(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].create({"name": "Control WIP", "code": "CWIP"})
        cls.other_warehouse = cls.env["stock.warehouse"].create({"name": "Otra WIP", "code": "OWIP"})
        cls.config = cls.env["sng.cycle.count.config"].create({
            "name": "Control WIP", "location_ids": [fields.Command.set(cls.warehouse.lot_stock_id.ids)],
            "min_days_between_counts": 0,
        })
        cls.operator = new_test_user(cls.env, login="wip.operator", groups="sng_cycle_count.group_cycle_count_operator")
        cls.supervisor = new_test_user(cls.env, login="wip.supervisor", groups="sng_cycle_count.group_cycle_count_supervisor")
        cls.manager = new_test_user(cls.env, login="wip.manager", groups="sng_cycle_count.group_cycle_count_management,sng_inventory_adjustment_history.group_inventory_adjustment_approver")
        cls.warehouse.cycle_supervisor_id = cls.supervisor
        cls.calendar = cls.env["resource.calendar"].create({"name": "Calendario WIP", "tz": "America/Costa_Rica"})
        cls.warehouse.cycle_calendar_id = cls.calendar

    def setUp(self):
        super().setUp()
        self.patch(self.env.registry["sng.cycle.count"], "_generate_discrepancy_reports", lambda s: True)

    def _quant(self, warehouse=None):
        warehouse = warehouse or self.warehouse
        product = self.env["product.product"].create({"name": "Artículo cíclico", "is_storable": True, "standard_price": 10})
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 10)
        return self.env["stock.quant"].search([("product_id", "=", product.id), ("location_id", "=", warehouse.lot_stock_id.id)])

    def _count(self, warehouse=None, assigned=True, with_line=True):
        warehouse = warehouse or self.warehouse
        vals = {"config_id": self.config.id, "count_date": fields.Date.today(),
                "warehouse_id": warehouse.id, "user_id": self.operator.id if assigned else False}
        if with_line:
            vals["line_ids"] = [fields.Command.create({"quant_id": self._quant(warehouse).id})]
        return self.env["sng.cycle.count"].with_user(self.supervisor).create(vals)

    def _capture(self, count, qty=8):
        count.line_ids.with_user(self.operator).write({"counted_qty": qty, "notes": "Conteo físico"})

    def _review(self, count):
        count.with_user(self.operator).action_submit_for_approval()
        count.line_ids.with_user(self.supervisor).write({"review_reason": "Se comprobó el faltante físicamente."})
        count.line_ids.with_user(self.supervisor).action_review_approve()
        count.with_user(self.supervisor).action_send_management()

    def test_third_order_has_initial_lines_and_fourth_is_blocked(self):
        counts = [self._count() for _ in range(3)]
        self.assertEqual(len(counts[2].line_ids), 1)
        for assigned in (True, False):
            with self.assertRaisesRegex(UserError, "3 o más"), self.cr.savepoint():
                self._count(assigned=assigned)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["sng.cycle.count.line"].with_user(self.supervisor).create({
                "cycle_count_id": counts[0].id, "quant_id": self._quant().id,
            })
        counts[0].with_user(self.operator).action_start()
        self._capture(counts[0])
        self._review(counts[0])
        counts[0].with_user(self.manager).action_approve()
        self.assertEqual(self._count().state, "draft")

    def test_slots_independent_and_unassignment_does_not_free_slot(self):
        counts = [self._count(with_line=False) for _ in range(3)]
        counts[0].with_user(self.supervisor).write({"user_id": False})
        self.assertTrue(counts[0].wip_started)
        with self.assertRaises(UserError), self.cr.savepoint():
            self._count()
        other = self._count(self.other_warehouse)
        self.assertEqual(other.warehouse_id, self.other_warehouse)
        counts[0].with_user(self.manager).write({"cancellation_reason": "Sesión duplicada"})
        counts[0].with_user(self.manager).action_cancel()
        self._count()

    def test_unassigned_order_consumes_slot_on_assignment(self):
        pending = self._count(assigned=False)
        self.assertFalse(pending.wip_started)
        for _ in range(3):
            self._count()
        with self.assertRaises(UserError), self.cr.savepoint():
            pending.with_user(self.supervisor).write({"user_id": self.operator.id})
        with self.assertRaises(UserError), self.cr.savepoint():
            pending.with_user(self.operator).action_start()

    def test_calendar_boundaries_weekends_and_holidays(self):
        # Monday 10:00 Costa Rica => Wednesday 07:30 / 17:00 Costa Rica.
        self.assertEqual(self.warehouse._cycle_deadlines(datetime(2026, 9, 7, 16)),
                         (datetime(2026, 9, 9, 13, 30), datetime(2026, 9, 9, 23)))
        for instant in (datetime(2026, 9, 11, 16), datetime(2026, 9, 12, 18)):
            self.assertEqual(self.warehouse._cycle_deadlines(instant)[1], datetime(2026, 9, 15, 23))
        self.env["resource.calendar.leaves"].create({
            "name": "Feriado de prueba", "calendar_id": self.calendar.id,
            "date_from": "2026-09-15 06:00:00", "date_to": "2026-09-16 06:00:00",
        })
        self.assertEqual(self.warehouse._cycle_deadlines(datetime(2026, 9, 11, 16))[1], datetime(2026, 9, 16, 23))
        self.assertEqual(self.warehouse._cycle_deadlines(datetime(2026, 9, 8, 2))[1], datetime(2026, 9, 9, 23))

    def test_warning_red_and_search_use_current_time(self):
        count = self._count()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 9, 7, 16)):
            self._capture(count)
        line = count.line_ids
        for now, yellow, red in [(datetime(2026, 9, 9, 13, 29), False, False),
                                 (datetime(2026, 9, 9, 13, 30), True, False),
                                 (datetime(2026, 9, 9, 23), True, False),
                                 (datetime(2026, 9, 9, 23, 0, 1), False, True)]:
            with patch.object(fields.Datetime, "now", return_value=now):
                line.invalidate_recordset(["is_warning", "is_overdue"])
                self.assertEqual((line.is_warning, line.is_overdue), (yellow, red))
                self.assertEqual(bool(line.search([("id", "=", line.id), ("is_overdue", "=", True)])), red)
                self.assertEqual(bool(line.search([("id", "=", line.id), ("is_warning", "=", True)])), yellow)

    def test_review_recount_keeps_deadline_and_requires_new_signoff(self):
        count = self._count()
        self._capture(count)
        deadline = count.line_ids.deadline_at
        self._review(count)
        line = count.line_ids.with_user(self.supervisor)
        line._return_for_recount("Confirmar empaque")
        self.assertEqual(line.review_state, "recount")
        self._capture(count, 10)
        self.assertEqual(line.deadline_at, deadline)
        self.assertTrue(line.unresolved)
        self.assertFalse(line.reviewed_by_id)
        self.assertEqual(line.difference_qty, 0)
        self._review(count)
        count.with_user(self.manager).action_approve()
        self.assertFalse(line.unresolved)
        self.assertFalse(line.quant_id.sng_cycle_line_id)
        self.assertEqual(line.applied_by_id, self.manager)
        self.assertEqual(len(line.capture_ids.filtered(lambda e: e.event == "capture")), 2)

    def test_operator_and_self_approval_guards(self):
        count = self._count()
        line = count.line_ids
        for method in ("action_copy_theoretical", "action_open_add_product_wizard", "action_cancel"):
            with self.assertRaises(AccessError):
                getattr(count.with_user(self.operator), method)()
        with self.assertRaises(AccessError):
            line.with_user(self.operator).write({"deadline_at": fields.Datetime.now()})
        with self.assertRaises(AccessError):
            line.with_user(self.operator).write({"state": "adjusted"})
        with self.assertRaises(AccessError):
            line.with_user(self.operator).create({"cycle_count_id": count.id, "quant_id": self._quant().id})
        line.with_user(self.manager).write({"counted_qty": 7})
        count.with_user(self.operator).action_submit_for_approval()
        line.with_user(self.manager).write({"review_reason": "No debe autoaprobar"})
        with self.assertRaises(AccessError):
            line.with_user(self.manager).action_review_approve()
        line.with_user(self.supervisor).action_review_approve()
        count.with_user(self.supervisor).action_send_management()
        with self.assertRaises(AccessError):
            count.with_user(self.manager).action_approve()
        count._system_write({"user_id": self.supervisor.id})
        with self.assertRaises(AccessError):
            count.with_user(self.manager).action_approve()

    def test_native_capture_zero_and_manual_collision(self):
        count = self._count()
        line = count.line_ids
        quant = line.quant_id.with_user(self.operator)
        quant.write({"inventory_quantity": 0, "sng_adjustment_reason": "No se encontró"})
        self.assertEqual(line.counted_qty, 0)
        self.assertEqual(line.difference_qty, -10)
        self.assertEqual(line.state, "counted")
        self.assertEqual(line.last_counted_by_id, self.operator)
        self.assertEqual(quant.quantity, 10)
        self.assertTrue(quant.sng_cycle_pending)
        self.assertEqual(quant.sng_cycle_deadline, line.deadline_at)
        self._capture(count, 6)
        self.assertEqual(quant.inventory_quantity, 6)
        with self.assertRaises(UserError):
            quant.action_request_inventory_approval()
        with self.assertRaises(UserError):
            self.env["sng.inventory.adjustment.request"].with_user(self.operator).create({
                "quant_id": quant.id, "counted_quantity": 6, "reason": "Intento alternativo",
            })
        with self.assertRaises(UserError):
            quant.with_user(self.manager).action_apply_inventory()

    def test_justification_required_and_capture_invalidates_review(self):
        count = self._count()
        self._capture(count)
        line = count.line_ids.with_user(self.supervisor)
        with self.assertRaises(UserError):
            line.action_review_approve()
        line.write({"review_reason": "Verificado"})
        line.action_review_approve()
        self._capture(count, 9)
        self.assertFalse(line.reviewed_by_id)
        self.assertEqual(line.review_state, "review")
        with self.assertRaises(UserError):
            count.with_user(self.manager).action_approve()

    def test_rounding_and_no_difference_does_not_start_clock(self):
        count = self._count()
        self._capture(count, 10)
        self.assertFalse(count.line_ids.first_difference_at)
        self._capture(count, 10 + count.line_ids.product_uom_id.rounding / 10)
        self.assertFalse(count.line_ids.first_difference_at)
        self._capture(count, 0)
        self.assertTrue(count.line_ids.first_difference_at)

    def test_overdue_activity_is_unique_and_closed(self):
        count = self._count()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 1, 5, 16)):
            self._capture(count)
        self.env["sng.cycle.count"]._cron_overdue_counts()
        self.env["sng.cycle.count"]._cron_overdue_counts()
        activity = count.activity_search(["sng_cycle_count.mail_activity_cycle_count_overdue"])
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity.user_id, self.supervisor)
        self._review(count)
        count.with_user(self.manager).action_approve()
        self.assertFalse(activity.exists())

    def test_stock_conflict_keeps_whole_session_unapplied(self):
        count = self._count()
        second = self.env["sng.cycle.count.line"].with_user(self.supervisor).create({
            "cycle_count_id": count.id, "quant_id": self._quant().id,
        })
        self._capture(count)
        self._review(count)
        second.quant_id._update_available_quantity(second.product_id, second.location_id, 1)
        with self.assertRaises(UserError):
            count.with_user(self.manager).action_approve()
        self.assertEqual(count.state, "pending_approval")
        self.assertEqual(sorted(count.line_ids.quant_id.mapped("quantity")), [10, 11])
        self.assertFalse(any(count.line_ids.mapped("applied_at")))

    def test_migration_grace_is_not_renewed(self):
        count = self._count()
        self._capture(count)
        self.env["ir.config_parameter"].sudo().search([("key", "=", "sng_cycle_count.control_migrated_at")]).unlink()
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 9, 7, 16)):
            self.env["sng.cycle.count"]._migrate_cycle_controls()
        self.assertEqual(count.line_ids.deadline_at, datetime(2026, 9, 9, 23))
        with patch.object(fields.Datetime, "now", return_value=datetime(2026, 9, 10, 16)):
            self.env["sng.cycle.count"]._migrate_cycle_controls()
        self.assertEqual(count.line_ids.deadline_at, datetime(2026, 9, 9, 23))

    def test_cron_skips_full_warehouse_and_generates_other(self):
        self.env["sng.cycle.count.config"].search([]).write({"active": False})
        for _ in range(3):
            self._count(with_line=False)
        self._quant()
        other = self._quant(self.other_warehouse)
        self.config.write({"active": True, "user_id": self.operator.id,
                           "location_ids": [fields.Command.set((self.warehouse.lot_stock_id | self.other_warehouse.lot_stock_id).ids)]})
        self.config.cron_generate_daily_counts()
        self.assertTrue(other.sng_cycle_line_id)
        self.assertEqual(other.sng_cycle_id.warehouse_id, self.other_warehouse)

    def test_review_from_form_and_native_default_filter(self):
        count = self._count()
        self._capture(count)
        count.line_ids.with_user(self.operator).action_send_for_review()
        self.assertEqual(count.state, "pending_review")
        with Form(count.with_user(self.supervisor)) as form:
            with form.line_ids.edit(0) as row:
                row.review_reason = "Verificado desde la pantalla de Jefatura"
        count.line_ids.with_user(self.supervisor).action_review_approve()
        count.with_user(self.supervisor).action_send_management()
        quant_model = self.env["stock.quant"].with_user(self.operator)
        action = quant_model.action_view_inventory()
        self.assertEqual(action["context"]["search_default_cycle_pending"], 1)
        self.assertFalse(action["context"]["search_default_my_count"])
        self.assertIn(count.line_ids.quant_id, quant_model.search([("sng_cycle_pending", "=", True)]))
        view = quant_model.get_view(view_id=self.env.ref("stock.view_stock_quant_tree_inventory_editable").id, view_type="list")
        tree = etree.fromstring(view["arch"])
        self.assertIn("sng_cycle_deadline", tree.get("default_order"))

    def test_review_reason_is_immutable_after_signoff(self):
        count = self._count()
        self._capture(count)
        self._review(count)
        with self.assertRaises(UserError):
            count.line_ids.with_user(self.supervisor).write({"review_reason": "Alterado"})

    def test_capture_records_cannot_be_forged_or_deleted(self):
        count = self._count()
        self._capture(count)
        event = count.line_ids.capture_ids[:1].with_user(self.supervisor)
        with self.assertRaises(AccessError):
            event.write({"quantity": 100})
        with self.assertRaises(AccessError):
            event.unlink()
        with self.assertRaises(AccessError):
            event.create({"line_id": count.line_ids.id, "user_id": self.manager.id,
                          "event": "capture", "quantity": 8})

    def test_operator_cannot_add_native_product_without_inventory_context(self):
        product = self.env["product.product"].create({"name": "No autorizado", "is_storable": True})
        for context in ({}, {"inventory_mode": True}):
            with self.assertRaises(AccessError):
                self.env["stock.quant"].with_user(self.operator).with_context(**context).create({
                    "product_id": product.id, "location_id": self.warehouse.lot_stock_id.id,
                })

    def test_migration_keeps_legacy_multiple_warehouses_and_unassigned_slot(self):
        count = self._count(assigned=False)
        second = self.env["sng.cycle.count.line"].create({"cycle_count_id": count.id, "quant_id": self._quant().id})
        old_quant = second.quant_id
        # Reproduce the shape allowed by the former module, before warehouse guards.
        second._control_write({"quant_id": self._quant(self.other_warehouse).id})
        old_quant.sudo().write({"sng_cycle_line_id": False})
        self.env["ir.config_parameter"].sudo().search([("key", "=", "sng_cycle_count.control_migrated_at")]).unlink()
        self.env["sng.cycle.count"]._migrate_cycle_controls()
        self.assertTrue(count.wip_started)
        self.assertEqual(count.wip_warehouse_ids, self.warehouse | self.other_warehouse)
        for _ in range(2):
            self._count(self.other_warehouse, with_line=False)
        with self.assertRaises(UserError), self.cr.savepoint():
            self._count(self.other_warehouse, with_line=False)
