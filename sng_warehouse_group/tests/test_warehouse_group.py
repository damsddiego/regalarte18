# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestWarehouseGroup(TransactionCase):
    def test_group_requires_warehouse(self):
        with self.assertRaises(ValidationError):
            self.env["sng.warehouse.group"].create({"name": "Sin almacenes"})

    def test_group_stores_warehouses(self):
        warehouses = self.env["stock.warehouse"].search([], limit=2)
        group = self.env["sng.warehouse.group"].create(
            {
                "name": "Principales",
                "warehouse_ids": [(6, 0, warehouses.ids)],
            }
        )
        self.assertEqual(group.warehouse_ids, warehouses)
