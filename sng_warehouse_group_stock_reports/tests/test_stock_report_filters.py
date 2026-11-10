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

    def test_get_stock_report_groups_lists_active_groups_with_warehouses(self):
        inactive = self.env["sng.warehouse.group"].create(
            {
                "name": "Grupo inactivo",
                "warehouse_ids": [(6, 0, self.warehouses.ids)],
                "active": False,
            }
        )
        result = self.env["sng.warehouse.group"].get_stock_report_groups()
        by_id = {item["id"]: item for item in result}
        self.assertIn(self.group.id, by_id)
        self.assertNotIn(inactive.id, by_id)
        self.assertEqual(by_id[self.group.id]["name"], "Grupo para filtros nativos")
        self.assertEqual(
            sorted(by_id[self.group.id]["warehouse_ids"]), sorted(self.warehouses.ids)
        )
        for item in result:
            self.assertEqual(set(item), {"id", "name", "warehouse_ids"})

    def test_inventory_at_date_uses_report_list_with_panel(self):
        wizard = self.env["stock.quantity.history"].create({})
        action = wizard.with_context(warehouse_id=self.warehouses.ids).open_at_date()
        list_view_id = self.env.ref(
            "sng_warehouse_group_stock_reports.view_stock_product_tree_at_date"
        ).id
        self.assertEqual(action["views"][0], (list_view_id, "list"))
        self.assertEqual(
            action["search_view_id"][0],
            self.env.ref("stock.product_search_form_view_stock_report").id,
        )
        self.assertEqual(action["context"]["to_date"], wizard.inventory_datetime)
        self.assertEqual(action["context"]["warehouse_id"], self.warehouses.ids)
        arch = self.env["product.product"].get_view(list_view_id, "list")["arch"]
        self.assertIn('js_class="stock_report_list_view"', arch)
