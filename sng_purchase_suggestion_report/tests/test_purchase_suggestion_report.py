# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestPurchaseSuggestionReport(TransactionCase):
    def test_analysis_days_is_inclusive(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-16",
                "coverage_days": 30,
            }
        )
        self.assertEqual(wizard._get_analysis_days(), 16)

    def test_avg_calculation_days_clamps_to_operations_start(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-01-01",
                "date_to": "2026-04-30",
                "coverage_days": 30,
            }
        )
        # Aunque el rango son 120 dias, el promedio se calcula desde
        # 2026-04-01 (inicio de operaciones), es decir 30 dias.
        self.assertEqual(wizard._get_analysis_days(), 120)
        self.assertEqual(wizard._get_avg_calculation_days(), 30)

    def test_avg_calculation_days_within_operations_period(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-16",
                "coverage_days": 30,
            }
        )
        self.assertEqual(wizard._get_avg_calculation_days(), 16)

    def test_warehouse_group_selects_warehouses(self):
        warehouses = self.env["stock.warehouse"].search([], limit=2)
        group = self.env["sng.warehouse.group"].create(
            {
                "name": "Principales",
                "warehouse_ids": [(6, 0, warehouses.ids)],
            }
        )
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-16",
                "warehouse_group_id": group.id,
            }
        )
        self.assertEqual(wizard._get_selected_warehouses(), warehouses)
        self.assertEqual(wizard._get_filter_summary()["warehouse_group"], group.display_name)

    def test_product_report_name_excludes_default_code(self):
        product = self.env["product.product"].create(
            {
                "name": "Producto para reporte",
                "default_code": "COD-REPORTE",
            }
        )
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-16",
            }
        )
        self.assertEqual(wizard._get_product_report_name(product), "Producto para reporte")

    def test_outlier_detected_when_current_avg_exceeds_threshold(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "outlier_threshold": 2.0,
                "min_history_months": 2,
            }
        )
        history_map = {1: [10.0, 12.0, 11.0]}
        self.assertTrue(wizard._is_product_outlier(1, 100.0, history_map))

    def test_outlier_not_detected_within_normal_range(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "outlier_threshold": 2.0,
                "min_history_months": 2,
            }
        )
        history_map = {1: [10.0, 12.0, 11.0]}
        self.assertFalse(wizard._is_product_outlier(1, 11.0, history_map))

    def test_outlier_not_detected_with_insufficient_history(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "outlier_threshold": 2.0,
                "min_history_months": 2,
            }
        )
        history_map = {1: [10.0]}
        self.assertFalse(wizard._is_product_outlier(1, 1000.0, history_map))

    def test_outlier_with_zero_standard_deviation(self):
        wizard = self.env["sng.purchase.suggestion.wizard"].create(
            {
                "date_from": "2026-04-01",
                "date_to": "2026-04-30",
                "outlier_threshold": 2.0,
                "min_history_months": 2,
            }
        )
        history_map = {1: [10.0, 10.0]}
        self.assertTrue(wizard._is_product_outlier(1, 11.0, history_map))
        self.assertFalse(wizard._is_product_outlier(1, 10.0, history_map))

    def test_outlier_threshold_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self.env["sng.purchase.suggestion.wizard"].create(
                {
                    "date_from": "2026-04-01",
                    "date_to": "2026-04-30",
                    "outlier_threshold": -1.0,
                }
            )

    def test_min_history_months_must_be_at_least_two(self):
        with self.assertRaises(ValidationError):
            self.env["sng.purchase.suggestion.wizard"].create(
                {
                    "date_from": "2026-04-01",
                    "date_to": "2026-04-30",
                    "min_history_months": 1,
                }
            )
