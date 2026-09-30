# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestProductCodeUnique(TransactionCase):
    def test_duplicate_default_code_is_blocked(self):
        self.env["product.product"].create(
            {"name": "Producto A", "default_code": "SNG-UNIQUE-001"}
        )

        with self.assertRaises(ValidationError):
            self.env["product.product"].create(
                {"name": "Producto B", "default_code": "SNG-UNIQUE-001"}
            )

    def test_duplicate_archived_product_code_is_blocked(self):
        product = self.env["product.product"].create(
            {"name": "Producto archivado", "default_code": "SNG-UNIQUE-002"}
        )
        product.product_tmpl_id.active = False

        with self.assertRaises(ValidationError):
            self.env["product.product"].create(
                {"name": "Producto nuevo", "default_code": "SNG-UNIQUE-002"}
            )

    def test_products_without_default_code_are_allowed(self):
        products = self.env["product.product"].create(
            [
                {"name": "Producto sin referencia A"},
                {"name": "Producto sin referencia B"},
            ]
        )

        self.assertEqual(len(products), 2)
