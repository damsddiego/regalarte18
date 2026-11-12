# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestValuationAnomaly(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.watchdog = cls.env["sng.valuation.watchdog"]
        cls.Anomaly = cls.env["sng.valuation.anomaly"]
        cls.stock_loc = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        ).lot_stock_id
        cls.product = cls.env["product.product"].create({
            "name": "Prueba vigilante margen",
            "default_code": "TEST-VIG-MARGEN",
            "type": "consu",
            "is_storable": True,
            "list_price": 100.0,
            "standard_price": 90.0,
        })
        cls.product_cero = cls.env["product.product"].create({
            "name": "Prueba vigilante costo cero",
            "default_code": "TEST-VIG-CERO",
            "type": "consu",
            "is_storable": True,
            "list_price": 100.0,
            "standard_price": 0.0,
        })
        Quant = cls.env["stock.quant"]
        Quant._update_available_quantity(cls.product, cls.stock_loc, 10)
        Quant._update_available_quantity(cls.product_cero, cls.stock_loc, 5)

    def _lines(self, product, anomaly_type):
        return self.Anomaly.search([
            ("product_id", "=", product.id),
            ("anomaly_type", "=", anomaly_type),
            ("company_id", "=", self.company.id),
        ])

    def test_margen_detectado_y_resuelto(self):
        self.watchdog._refresh_anomalies(self.company, 0.8)
        line = self._lines(self.product, "margen")
        self.assertEqual(len(line), 1)
        self.assertEqual(line.qty_fisica, 10)
        self.assertEqual(line.costo, 90.0)
        self.assertAlmostEqual(line.margen_pct, 90.0)
        self.assertEqual(line.first_seen, fields.Date.context_today(line))

        self.product.list_price = 1000.0
        self.watchdog._refresh_anomalies(self.company, 0.8)
        self.assertFalse(self._lines(self.product, "margen"))

    def test_first_seen_se_conserva(self):
        self.watchdog._refresh_anomalies(self.company, 0.8)
        line = self._lines(self.product, "margen")
        old = fields.Date.context_today(line) - timedelta(days=10)
        line.first_seen = old
        self.watchdog._refresh_anomalies(self.company, 0.8)
        line = self._lines(self.product, "margen")
        self.assertEqual(len(line), 1)
        self.assertEqual(line.first_seen, old)
        self.assertEqual(line.dias, 10)

    def test_costo_cero(self):
        self.watchdog._refresh_anomalies(self.company, 0.8)
        line = self._lines(self.product_cero, "costo_cero")
        self.assertEqual(len(line), 1)
        self.assertEqual(line.qty_fisica, 5)

    def test_boton_actualizar(self):
        action = self.Anomaly.action_refresh()
        self.assertEqual(action.get("tag"), "reload")
        self.assertTrue(self._lines(self.product, "margen"))

    def test_cron_genera_correo_con_enlace(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("sng_valuation_watchdog.email_to", "prueba@example.com")
        icp.set_param("sng_valuation_watchdog.max_rows", "100000")  # que la fila de prueba no quede cortada
        self.watchdog.cron_run_checks()
        mail = self.env["mail.mail"].search(
            [("email_to", "=", "prueba@example.com")], order="id desc", limit=1
        )
        self.assertTrue(mail)
        self.assertIn("TEST-VIG-MARGEN", mail.body_html)
        self.assertIn("action-sng_valuation_watchdog.action_valuation_anomaly", mail.body_html)
