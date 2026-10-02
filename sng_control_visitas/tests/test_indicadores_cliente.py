# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests import tagged

from .common import ControlVisitasCommon


@tagged('post_install', '-at_install', 'sng_control_visitas')
class TestIndicadoresCliente(ControlVisitasCommon):

    def test_cliente_sin_compras_ni_metricas(self):
        seg = self._seguimiento()
        self.assertFalse(seg.fecha_ultima_compra)
        self.assertEqual(seg.dias_sin_comprar, 0)
        self.assertEqual(seg.monto_ultima_compra, 0.0)
        self.assertEqual(seg.promedio_trimestral, 0.0)
        self.assertEqual(seg.saldo_pendiente, 0.0)
        self.assertFalse(seg.indicadores_actualizados)

    def test_ultima_compra_y_saldo(self):
        self._factura(self.cliente, date.today() - timedelta(days=90))
        ultima = self._factura(self.cliente, date.today() - timedelta(days=40))
        self._factura(self.cliente2, date.today() - timedelta(days=5))
        seg = self._seguimiento()
        self.assertEqual(seg.fecha_ultima_compra,
                         date.today() - timedelta(days=40))
        self.assertEqual(seg.dias_sin_comprar, 40)
        self.assertEqual(seg.monto_ultima_compra, ultima.amount_total_signed)
        # dos facturas sin pagar del mismo cliente
        self.assertAlmostEqual(
            seg.saldo_pendiente, 2 * ultima.amount_total_signed, places=2)

    def test_metricas_visibles_sin_permiso_contable(self):
        self.env['regalarte.customer.metric'].create({
            'partner_id': self.cliente.id,
            'company_id': self.company.id,
            'currency_id': self.company.currency_id.id,
            'customer_current_month_sales': 100.0,
            'customer_previous_month_sales': 200.0,
            'customer_quarterly_avg_sales': 300.0,
            'customer_semiannual_avg_sales': 400.0,
            'customer_annual_avg_sales': 500.0,
            'customer_total_sales': 6000.0,
            'customer_dpp_days': 32.5,
        })
        self.cliente.phone = '2222-3333'
        # natalia no tiene grupo contable y el modelo de métricas sí lo exige
        seg = self._seguimiento().with_user(self.natalia)
        self.assertEqual(seg.partner_phone, '2222-3333')
        self.assertEqual(seg.venta_mes_actual, 100.0)
        self.assertEqual(seg.venta_mes_anterior, 200.0)
        self.assertEqual(seg.promedio_trimestral, 300.0)
        self.assertEqual(seg.promedio_semestral, 400.0)
        self.assertEqual(seg.promedio_anual, 500.0)
        self.assertEqual(seg.venta_acumulada, 6000.0)
        self.assertEqual(seg.dpp_dias, 32.5)

    def test_contacto_del_cliente_usa_cliente_comercial(self):
        ultima = self._factura(self.cliente, date.today() - timedelta(days=10))
        contacto = self.env['res.partner'].create({
            'name': 'Encargada', 'parent_id': self.cliente.id,
            'customer_rank': 1})
        seg = self._seguimiento(partner=contacto)
        self.assertEqual(seg.fecha_ultima_compra, ultima.invoice_date)
