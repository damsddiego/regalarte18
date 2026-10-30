# -*- coding: utf-8 -*-
import base64

from odoo import Command
from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestKeepXmlAmounts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1
        )
        cls.expense_account = cls.env["account.account"].create(
            {
                "name": "Gasto prueba XML",
                "code": "XFEX001",
                "account_type": "expense",
                "company_ids": [Command.set([company.id])],
            }
        )
        cls.payable_account = cls.env["account.account"].create(
            {
                "name": "CxP prueba XML",
                "code": "XFEX002",
                "account_type": "liability_payable",
                "reconcile": True,
                "company_ids": [Command.set([company.id])],
            }
        )
        cls.tax_xml = cls.env["account.tax"].create(
            {"name": "IVA XML 13", "amount": 13.0, "type_tax_use": "purchase", "company_id": company.id}
        )
        cls.tax_product = cls.env["account.tax"].create(
            {"name": "Otro impuesto 1", "amount": 1.0, "type_tax_use": "purchase", "company_id": company.id}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Nacionalizacion prueba",
                "type": "service",
                "standard_price": 999.0,
                "supplier_taxes_id": [Command.set([cls.tax_product.id])],
            }
        )
        cls.partner_keep = cls.env["res.partner"].create(
            {
                "name": "Agente aduanal",
                "supplier_rank": 1,
                "fe_keep_xml_line_amounts": True,
                "property_account_payable_id": cls.payable_account.id,
            }
        )
        cls.partner_normal = cls.env["res.partner"].create(
            {
                "name": "Proveedor normal",
                "supplier_rank": 1,
                "property_account_payable_id": cls.payable_account.id,
            }
        )

    def _create_xml_bill(self, partner):
        """Factura como la deja el importador: línea sin producto con montos del XML."""
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "journal_id": self.journal.id,
                "invoice_date": "2026-10-29",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "GASTOS DE ZONA",
                            "quantity": 1.0,
                            "price_unit": 16500.0,
                            "account_id": self.expense_account.id,
                            "tax_ids": [Command.set([self.tax_xml.id])],
                        }
                    ),
                ],
            }
        )
        bill.invoice_line_ids.fe_xml_line = True
        return bill

    def _set_product_on_first_line(self, bill):
        with Form(bill) as form:
            with form.invoice_line_ids.edit(0) as line:
                line.product_id = self.product
        return bill.invoice_line_ids[0]

    def test_partner_marcado_conserva_precio_cantidad_e_impuestos(self):
        bill = self._create_xml_bill(self.partner_keep)
        line = self._set_product_on_first_line(bill)

        self.assertEqual(line.product_id, self.product)
        self.assertEqual(line.price_unit, 16500.0)
        self.assertEqual(line.quantity, 1.0)
        self.assertEqual(line.tax_ids, self.tax_xml)
        self.assertEqual(line.price_subtotal, 16500.0)
        self.assertEqual(bill.amount_total, 18645.0)

    def test_partner_sin_marca_recalcula_como_odoo(self):
        bill = self._create_xml_bill(self.partner_normal)
        line = self._set_product_on_first_line(bill)

        self.assertEqual(line.price_unit, 999.0)
        self.assertEqual(line.tax_ids, self.tax_product)

    def test_linea_manual_en_proveedor_marcado_recalcula_como_odoo(self):
        bill = self._create_xml_bill(self.partner_keep)
        with Form(bill) as form:
            with form.invoice_line_ids.new() as line:
                line.product_id = self.product
        manual = bill.invoice_line_ids.filtered(lambda l: not l.fe_xml_line and l.display_type == "product")

        self.assertEqual(len(manual), 1)
        self.assertEqual(manual.price_unit, 999.0)
        self.assertEqual(manual.tax_ids, self.tax_product)

    def test_marcar_lineas_xml_solo_lineas_producto_con_xml(self):
        bill = self._create_xml_bill(self.partner_keep)
        bill.invoice_line_ids.fe_xml_line = False
        bill.write(
            {
                "xml_supplier_approval": base64.b64encode(b"<FacturaElectronica/>"),
                "invoice_line_ids": [Command.create({"name": "Nota", "display_type": "line_note"})],
            }
        )
        sin_xml = self._create_xml_bill(self.partner_keep)
        sin_xml.invoice_line_ids.fe_xml_line = False

        (bill | sin_xml)._sng_mark_xml_lines()

        product_lines = bill.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        note_lines = bill.invoice_line_ids.filtered(lambda l: l.display_type == "line_note")
        self.assertTrue(all(product_lines.mapped("fe_xml_line")))
        self.assertFalse(any(note_lines.mapped("fe_xml_line")))
        self.assertFalse(any(sin_xml.invoice_line_ids.mapped("fe_xml_line")))
