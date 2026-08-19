# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestComparativoWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wizard = cls.env["sng.comparativo.wizard"].create(
            {"fecha_referencia": "2026-06-10"}
        )

    def test_warehouse_group_selects_warehouses_and_locations(self):
        warehouses = self.env["stock.warehouse"].search([], limit=2)
        group = self.env["sng.warehouse.group"].create(
            {
                "name": "Almacenes comparativo",
                "warehouse_ids": [(6, 0, warehouses.ids)],
            }
        )
        wizard = self.env["sng.comparativo.wizard"].create(
            {
                "fecha_referencia": "2026-06-10",
                "warehouse_group_id": group.id,
            }
        )

        self.assertEqual(wizard._get_selected_warehouses(), warehouses)
        locations = self.env["stock.location"].browse(wizard._get_location_ids())
        self.assertTrue(locations)
        self.assertTrue(
            all(
                any(
                    location.parent_path.startswith(warehouse.view_location_id.parent_path)
                    for warehouse in warehouses
                )
                for location in locations
            )
        )

    def test_add_product_prices_adds_cost_and_sales_price(self):
        product = self.env["product.product"].create(
            {
                "name": "Producto comparativo",
                "standard_price": 12.5,
                "list_price": 20.0,
            }
        )

        rows = self.wizard._add_product_prices([{"product_id": product.id}])

        self.assertEqual(rows[0]["costo"], product.standard_price)
        self.assertEqual(rows[0]["precio"], product.lst_price)

    def test_add_product_prices_hides_cost_without_security_group(self):
        user = self.env["res.users"].create(
            {
                "name": "Usuario sin costo comparativo",
                "login": "comparativo_sin_costo",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "Producto costo protegido",
                "standard_price": 18.0,
                "list_price": 30.0,
            }
        )

        rows = self.wizard.with_user(user)._add_product_prices([{"product_id": product.id}])

        self.assertEqual(rows[0]["costo"], 0.0)
        self.assertEqual(rows[0]["precio"], product.lst_price)
