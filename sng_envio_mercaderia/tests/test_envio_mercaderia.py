# -*- coding: utf-8 -*-

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEnvioMercaderia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usual_method = cls.env["res.partner.delivery.type"].create(
            {
                "name": "Cordero Test Auditoría",
                "code": "CORDERO_TEST",
                "company_id": cls.env.company.id,
            }
        )
        cls.other_method = cls.env["res.partner.delivery.type"].create(
            {
                "name": "Mensajería Test Auditoría",
                "code": "PROPIA_TEST",
                "company_id": cls.env.company.id,
            }
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Cliente auditoría"}
        )
        cls.delivery_contact = cls.env["res.partner"].create(
            {
                "name": "Sucursal de entrega",
                "parent_id": cls.customer.id,
                "type": "delivery",
                "street": "Frente al BCR",
                "phone": "2222-3333",
                "delivery_type_id": cls.usual_method.id,
            }
        )
        cls.picker = cls.env["res.partner"].create({"name": "Persona de bodega"})
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.customer.id,
                "partner_invoice_id": cls.customer.id,
                "partner_shipping_id": cls.delivery_contact.id,
                "shipping_method": "Cordero Test Auditoría",
            }
        )

    def _create_mobile_audit(self, **overrides):
        values = {
            "source_model": "sale.order",
            "source_id": self.order.id,
            "box_number": 1,
            "box_total": 2,
            "delivery_type_id": self.other_method.id,
            "picker_partner_id": self.picker.id,
            "request_key": self._testMethodName,
        }
        values.update(overrides)
        return self.env["sng.envio.mercaderia"].mobile_create_or_get(**values)

    def test_mobile_creation_is_idempotent_and_audits_change(self):
        first = self._create_mobile_audit()
        second = self._create_mobile_audit()

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["boxes_label"], "1 CAJA DE 2")
        self.assertEqual(first["customer_delivery_method"], "Cordero Test Auditoría")
        self.assertEqual(first["delivery_method"], "Mensajería Test Auditoría")
        self.assertEqual(first["delivery_method_status"], "changed")
        self.assertTrue(first["delivery_method_changed"])
        self.assertEqual(first["picker_name"], "Persona de bodega")

    def test_transportista_de_ventas_se_guarda_y_preselecciona(self):
        producto = self.env["product.product"].create({
            "name": "Servicio de envío de prueba", "type": "service",
        })
        carrier = self.env["delivery.carrier"].create({
            "name": "Método ventas de prueba", "product_id": producto.id,
        })
        metodos = self.env["sng.envio.mercaderia"].mobile_get_carrier_methods(
            "sale.order", self.order.id
        )
        self.assertIn(carrier.id, [m["id"] for m in metodos])
        payload = self._create_mobile_audit(
            delivery_type_id=carrier.id, delivery_carrier_id=carrier.id,
            confirm=True,
        )
        audit = self.env["sng.envio.mercaderia"].browse(payload["id"])
        audit.action_set_customer_default(actor_partner_id=self.picker.id)
        self.assertEqual(
            self.customer.with_company(self.order.company_id).property_delivery_carrier_id,
            carrier,
        )
        defaults = self.env["sng.envio.mercaderia"].mobile_get_carrier_defaults(
            "sale.order", self.order.id
        )
        self.assertEqual(defaults["suggested_delivery_type_id"], carrier.id)
        otro = self.env["delivery.carrier"].create({
            "name": "Otro método de ventas", "product_id": producto.id,
        })
        cambio = self._create_mobile_audit(
            delivery_type_id=otro.id, delivery_carrier_id=otro.id,
            request_key="otro-metodo", confirm=True,
        )
        self.assertEqual(cambio["delivery_method_status"], "changed")
        self.env["sng.envio.mercaderia"].browse(cambio["id"]).action_set_customer_default(
            actor_partner_id=self.picker.id
        )
        self.assertEqual(
            self.customer.with_company(self.order.company_id).property_delivery_carrier_id,
            otro,
        )
        defaults = self.env["sng.envio.mercaderia"].mobile_get_carrier_defaults(
            "sale.order", self.order.id
        )
        self.assertEqual(defaults["suggested_delivery_type_id"], otro.id)
        audit.action_set_customer_default(actor_partner_id=self.picker.id)
        self.assertEqual(
            self.customer.with_company(self.order.company_id).property_delivery_carrier_id,
            otro,
        )

    def test_confirmed_audit_is_locked(self):
        payload = self._create_mobile_audit(confirm=True)
        audit = self.env["sng.envio.mercaderia"].browse(payload["id"])

        with self.assertRaises(UserError):
            audit.write({"box_total": 3})

    def test_customer_default_can_be_updated_without_losing_history(self):
        payload = self._create_mobile_audit(confirm=True)
        audit = self.env["sng.envio.mercaderia"].browse(payload["id"])

        audit.action_set_customer_default(actor_partner_id=self.picker.id)

        self.assertEqual(self.delivery_contact.delivery_type_id, self.other_method)
        self.assertEqual(audit.customer_delivery_method, "Cordero Test Auditoría")
        self.assertTrue(audit.delivery_method_changed)
        self.assertTrue(audit.customer_method_updated)

    def test_same_customer_method_is_not_marked_as_changed(self):
        payload = self._create_mobile_audit(
            delivery_type_id=self.usual_method.id,
            request_key="same-method",
        )
        self.assertEqual(payload["delivery_method_status"], "usual")
        self.assertFalse(payload["delivery_method_changed"])

    def test_auditoria_anterior_sincroniza_transportista_equivalente(self):
        producto = self.env["product.product"].create({
            "name": "Servicio de envío anterior", "type": "service",
        })
        carrier = self.env["delivery.carrier"].create({
            "name": self.other_method.name, "product_id": producto.id,
        })
        payload = self._create_mobile_audit(confirm=True)
        self.env["sng.envio.mercaderia"].browse(payload["id"]).action_set_customer_default(
            actor_partner_id=self.picker.id
        )
        self.assertEqual(
            self.customer.with_company(self.order.company_id).property_delivery_carrier_id,
            carrier,
        )

    def test_box_number_cannot_exceed_total(self):
        with self.assertRaises(ValidationError):
            self._create_mobile_audit(
                box_number=3,
                box_total=2,
                request_key="invalid-boxes",
            )

    def test_print_registration_keeps_audit(self):
        payload = self._create_mobile_audit(confirm=True)
        audit = self.env["sng.envio.mercaderia"].browse(payload["id"])

        audit.action_register_print(actor_partner_id=self.picker.id)

        self.assertEqual(audit.print_count, 1)
        self.assertEqual(audit.last_printed_by_id, self.picker)
