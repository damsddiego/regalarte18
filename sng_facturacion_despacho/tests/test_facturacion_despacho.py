from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestFacturacionDespacho(AccountTestInvoicingCommon):
    def setUp(self):
        super().setUp()
        self.ventas = self.env["sale.order"]
        self.env.user.sudo().groups_id = [
            Command.link(self.env.ref("sng_facturacion_despacho.group_facturar_despacho").id)
        ]
        self.parametro = "sng_facturacion_despacho.habilitada.%s" % self.env.company.id
        self.env["ir.config_parameter"].sudo().set_param(self.parametro, "1")
        cliente = self.env["res.partner"].create({"name": "Cliente prueba despacho"})
        producto = self.env["product.product"].create({
            "name": "Producto prueba despacho",
            "type": "consu",
            "is_storable": True,
            "invoice_policy": "delivery",
        })
        self.orden = self.ventas.create({
            "partner_id": cliente.id,
            "order_line": [Command.create({
                "product_id": producto.id, "product_uom_qty": 2, "price_unit": 10,
            })],
        })
        self.orden.action_confirm()
        self.salida = self.orden.picking_ids.filtered(
            lambda p: p.location_dest_id.usage == "customer"
        )
        self.env["stock.quant"]._update_available_quantity(
            producto, self.salida.location_id, 2,
        )

    def _entregar(self, cantidad=2):
        self.salida.action_assign()
        self.salida.move_ids.quantity = cantidad
        self.salida.move_ids.picked = True
        self.salida.with_context(skip_backorder=True).button_validate()
        self.assertEqual(self.salida.state, "done")

    def test_la_orden_sin_salida_hecha_no_es_facturable_desde_la_app(self):
        estado = self.ventas.mobile_invoice_dispatch(self.orden.id, "prueba")
        self.assertEqual(estado["status"], "pending_delivery")
        self.assertFalse(self.orden.invoice_ids)

    def test_la_entrega_parcial_requiere_revision(self):
        self._entregar(1)
        estado = self.ventas.mobile_invoice_dispatch(self.orden.id, "prueba")
        self.assertEqual(estado["status"], "needs_review")
        self.assertFalse(self.orden.invoice_ids)

    def test_factura_cantidad_entregada_si_no_hay_salida_pendiente(self):
        self.orden.company_id.sudo().frm_ws_ambiente = "disabled"
        self.salida.action_assign()
        self.salida.move_ids.quantity = 1
        self.salida.move_ids.picked = True
        self.salida.with_context(
            skip_backorder=True, picking_ids_not_to_backorder=self.salida.ids
        ).button_validate()
        self.assertEqual(self.salida.state, "done")
        estado = self.ventas.mobile_invoice_dispatch(self.orden.id, "parcial")
        self.assertEqual(estado["status"], "posted")
        self.assertEqual(self.orden.invoice_ids.invoice_line_ids.quantity, 1)
        repetido = self.ventas.mobile_invoice_dispatch(self.orden.id, "reintento")
        self.assertEqual(repetido["status"], "posted")
        self.assertEqual(repetido["invoice_id"], estado["invoice_id"])
        self.assertEqual(len(self.orden.invoice_ids), 1)

    def test_entrega_con_linea_sin_entregar_se_puede_reconsultar(self):
        self.orden.company_id.sudo().frm_ws_ambiente = "disabled"
        faltante = self.env["product.product"].create({
            "name": "Producto no entregado", "type": "consu",
            "is_storable": True, "invoice_policy": "delivery",
        })
        self.env["sale.order.line"].create({
            "order_id": self.orden.id, "product_id": faltante.id,
            "product_uom_qty": 3, "price_unit": 10,
        })
        self.salida.action_assign()
        entregado = self.salida.move_ids.filtered(lambda m: m.product_id != faltante)
        entregado.quantity = 1
        entregado.picked = True
        self.salida.with_context(
            skip_backorder=True, picking_ids_not_to_backorder=self.salida.ids
        ).button_validate()
        resultado = self.ventas.mobile_invoice_dispatch(self.orden.id, "faltante")
        self.assertEqual(resultado["status"], "posted")
        factura = self.env["account.move"].browse(resultado["invoice_id"])
        self.assertNotIn(faltante, factura.invoice_line_ids.product_id)
        self.assertEqual(self.orden.invoice_status, "no")
        estado = self.ventas.mobile_get_dispatch_invoice_status(self.orden.id)
        self.assertEqual(estado["status"], "posted")
        repetido = self.ventas.mobile_invoice_dispatch(self.orden.id, "reintento-faltante")
        self.assertEqual(repetido["invoice_id"], factura.id)

    def test_devolucion_con_nota_de_credito_requiere_revision(self):
        self.orden.company_id.sudo().frm_ws_ambiente = "disabled"
        self._entregar()
        resultado = self.ventas.mobile_invoice_dispatch(self.orden.id, "entrega")
        factura = self.env["account.move"].browse(resultado["invoice_id"])
        asistente = self.env["stock.return.picking"].create({"picking_id": self.salida.id})
        devolucion = self.env["stock.picking"].browse(
            asistente.action_create_returns_all()["res_id"]
        )
        devolucion.move_ids.quantity = 2
        devolucion.move_ids.picked = True
        devolucion.button_validate()
        factura._reverse_moves().action_post()
        self.assertEqual(self.orden.order_line.qty_delivered, 0)
        self.assertEqual(self.orden.order_line.qty_to_invoice, 0)
        estado = self.ventas.mobile_get_dispatch_invoice_status(self.orden.id)
        self.assertEqual(estado["status"], "needs_review")

    def test_factura_contabilizada_con_ajuste_fiscal_se_puede_reconsultar(self):
        self.orden.company_id.sudo().frm_ws_ambiente = "disabled"
        self._entregar()
        factura = self.orden._create_invoices()
        producto = self.env["product.product"].create({
            "name": "IVA Devuelto", "type": "service",
        })
        factura.write({"invoice_line_ids": [Command.create({
            "name": "IVA Devuelto", "product_id": producto.id,
            "quantity": 1, "price_unit": -0.4,
        })]})
        factura.action_post()
        estado = self.ventas.mobile_get_dispatch_invoice_status(self.orden.id)
        self.assertEqual(estado["status"], "posted")
        self.assertEqual(estado["invoice_id"], factura.id)

    def test_validar_entrega_y_consultar_no_crea_factura(self):
        self._entregar()
        estado = self.ventas.mobile_get_dispatch_invoice_status(self.orden.id)
        self.assertEqual(estado["status"], "ready")
        self.assertFalse(self.orden.invoice_ids)

    def test_la_integracion_requiere_permiso_especifico(self):
        self.env.user.sudo().groups_id = [
            Command.unlink(self.env.ref("sng_facturacion_despacho.group_facturar_despacho").id)
        ]
        with self.assertRaises(AccessError):
            self.ventas.mobile_invoice_dispatch(self.orden.id, "prueba")
        self.assertEqual(
            self.ventas.mobile_get_dispatch_invoice_status(self.orden.id)["status"],
            "unavailable",
        )

    def test_borrador_con_cantidad_distinta_no_se_confirma(self):
        self._entregar()
        borrador = self.orden._create_invoices()
        borrador.invoice_line_ids.filtered(lambda l: l.display_type == "product").quantity = 3
        estado = self.ventas.mobile_invoice_dispatch(self.orden.id, "prueba")
        self.assertEqual(estado["status"], "needs_review")
        self.assertEqual(borrador.state, "draft")
        self.assertEqual(self.orden.invoice_ids, borrador)

    def test_borrador_de_otro_cliente_no_se_confirma(self):
        self._entregar()
        borrador = self.orden._create_invoices()
        borrador.partner_id = self.env["res.partner"].create({"name": "Otro cliente"})
        estado = self.ventas.mobile_invoice_dispatch(self.orden.id, "prueba")
        self.assertEqual(estado["status"], "needs_review")
        self.assertEqual(borrador.state, "draft")

    def test_facturar_dos_veces_conserva_una_factura_contabilizada(self):
        # Contabilización real sin transmitir un comprobante fiscal de prueba.
        self.orden.company_id.sudo().frm_ws_ambiente = "disabled"
        self._entregar()
        primero = self.ventas.mobile_invoice_dispatch(self.orden.id, "primero")
        segundo = self.ventas.mobile_invoice_dispatch(self.orden.id, "segundo")
        self.assertEqual(primero["status"], "posted")
        self.assertEqual(segundo["invoice_id"], primero["invoice_id"])
        self.assertEqual(len(self.orden.invoice_ids), 1)
        self.assertEqual(self.orden.invoice_ids.invoice_line_ids.quantity, 2)

    def test_error_fiscal_conserva_el_borrador_y_el_reintento_lo_reutiliza(self):
        self._entregar()
        # La llamada externa a Hacienda se reemplaza por un error fiscal determinista.
        with patch.object(type(self.env["account.move"]), "action_post",
                          side_effect=UserError("Falta CABYS")):
            primero = self.ventas.mobile_invoice_dispatch(self.orden.id, "primero")
            segundo = self.ventas.mobile_invoice_dispatch(self.orden.id, "reintento")
        self.assertEqual(primero["status"], "needs_review")
        self.assertEqual(primero["invoice_state"], "draft")
        self.assertEqual(primero["message"], "Falta CABYS")
        self.assertEqual(segundo["invoice_id"], primero["invoice_id"])
        self.assertEqual(len(self.orden.invoice_ids), 1)
