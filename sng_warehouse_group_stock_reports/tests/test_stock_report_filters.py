# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestStockReportWarehouseGroupFilters(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouses = cls.env["stock.warehouse"].search([], limit=2)
        cls.group = cls.env["sng.warehouse.group"].create(
            {
                "name": "Grupo para filtros nativos",
                "warehouse_ids": [(6, 0, cls.warehouses.ids)],
            }
        )

    def test_fields_are_search_only(self):
        for model_name in (
            "stock.quant",
            "stock.move",
            "stock.move.line",
            "stock.valuation.layer",
        ):
            field = self.env[model_name]._fields["warehouse_group_id"]
            self.assertFalse(field.store)
            self.assertTrue(field.search)

    def test_native_report_domains_are_valid(self):
        for model_name in (
            "stock.quant",
            "stock.move",
            "stock.move.line",
            "stock.valuation.layer",
        ):
            model = self.env[model_name]
            domain = model._search_warehouse_group_id("=", self.group.id)
            model.search_count(domain)

    def test_search_panels_list_warehouse_groups(self):
        for model_name in (
            "stock.quant",
            "stock.move",
            "stock.move.line",
            "stock.valuation.layer",
        ):
            result = self.env[model_name].search_panel_select_range(
                "warehouse_group_id",
                expand=True,
                hierarchize=False,
            )
            self.assertIn(self.group.id, [value["id"] for value in result["values"]])
