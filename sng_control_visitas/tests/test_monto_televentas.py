# -*- coding: utf-8 -*-
from odoo.tests import tagged

from .common import ControlVisitasCommon


@tagged('post_install', '-at_install', 'sng_control_visitas')
class TestMontoTeleventas(ControlVisitasCommon):

    def _orden(self, cantidad=2):
        producto = self.env['product.product'].create({
            'name': 'Prod TV', 'list_price': 100.0, 'type': 'consu',
            'invoice_policy': 'order'})
        so = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [(0, 0, {'product_id': producto.id,
                                   'product_uom_qty': cantidad})],
        })
        so.action_confirm()
        return so

    def test_sin_orden_el_monto_es_manual(self):
        seg = self._seguimiento(monto_venta=1200)
        self.assertEqual(seg.monto_venta, 1200)
        seg.write({'canal': 'llamada', 'resultado': 'venta_recuperada',
                   'comentario': 'Pedido por teléfono'})
        seg.action_marcar_realizado()
        self.assertEqual(seg.monto_venta, 1200)

    def test_orden_sin_factura_usa_total_de_la_orden(self):
        so = self._orden()
        seg = self._seguimiento(sale_order_id=so.id)
        self.assertTrue(so.amount_total)
        self.assertAlmostEqual(seg.monto_venta, so.amount_total)

    def test_orden_facturada_usa_monto_de_la_factura(self):
        so = self._orden(cantidad=2)
        seg = self._seguimiento()
        # la responsable de televentas no ve órdenes ajenas, igual se llena
        seg.with_user(self.natalia).write({'sale_order_id': so.id})
        self.assertAlmostEqual(seg.monto_venta, so.amount_total)
        # se factura solo la mitad del pedido
        factura = so._create_invoices()
        factura.invoice_line_ids.quantity = 1
        factura.action_post()
        self.assertLess(factura.amount_total_signed, so.amount_total)
        self.assertAlmostEqual(seg.monto_venta, factura.amount_total_signed)
        # una nota de crédito total deja el monto en cero
        nota = factura._reverse_moves([{'invoice_date': factura.invoice_date}])
        nota.action_post()
        self.assertAlmostEqual(seg.monto_venta, 0.0)

    def test_resultado_sin_venta_no_acredita_la_orden(self):
        """Una orden enlazada no cuenta si la gestión se cerró sin venta."""
        so = self._orden()
        seg = self._seguimiento(sale_order_id=so.id)
        # Pendiente: el monto se ve para preparar la llamada.
        self.assertAlmostEqual(seg.monto_venta, so.amount_total)
        seg.write({'canal': 'correo', 'resultado': 'datos_incorrectos',
                   'comentario': 'El correo no existe'})
        seg.action_marcar_realizado()
        self.assertEqual(seg.monto_venta, 0.0)
        self.assertEqual(seg.efectividad, 0.0)
        # Si después se corrige a venta recuperada, vuelve a contar.
        seg.write({'resultado': 'venta_recuperada'})
        self.assertAlmostEqual(seg.monto_venta, so.amount_total)

    def test_orden_cancelada_sin_factura_no_suma(self):
        so = self._orden()
        seg = self._seguimiento(sale_order_id=so.id)
        so._action_cancel()
        self.assertEqual(so.state, 'cancel')
        self.assertEqual(seg.monto_venta, 0.0)
