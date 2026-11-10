# -*- coding: utf-8 -*-

from io import BytesIO
from unittest import SkipTest
from unittest.mock import patch

from openpyxl import load_workbook

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestFacturacionClienteMensual(TransactionCase):
    """Fechas en 2027 para no chocar con los candados de la copia de Prod."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        company = cls.env.company
        # Publicar sin documento electrónico (sin CABYS ni datos de Hacienda)
        # y sin consumir sequence.DA: se conserva el nombre estándar.
        move_class = type(cls.env["account.move"])
        if hasattr(move_class, "_electronic_documents_disabled"):
            cls.startClassPatcher(
                patch.object(move_class, "_electronic_documents_disabled", lambda self: True)
            )
            cls.startClassPatcher(
                patch.object(move_class, "_next_disabled_document_sequence", lambda self: False)
            )
        if "payment_method_default_id" in company._fields:
            payment_method = cls.env.ref(
                "cr_electronic_invoice.PaymentMethods_1", raise_if_not_found=False
            )
            if payment_method:
                company.payment_method_default_id = payment_method
        cls.income_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "income"),
                ("company_ids", "in", company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        cls.receivable_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "asset_receivable"),
                ("company_ids", "in", company.id),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        cls.sale_tax = cls.env["account.tax"].search(
            [
                ("company_id", "=", company.id),
                ("type_tax_use", "=", "sale"),
                ("amount_type", "=", "percent"),
                ("amount", ">", 0),
                ("price_include", "=", False),
                ("active", "=", True),
            ],
            limit=1,
        )
        cls.product = cls.env["product.product"].search(
            [("active", "=", True), ("sale_ok", "=", True)], limit=1
        )
        if not (cls.income_account and cls.receivable_account and cls.product):
            raise SkipTest("Faltan cuentas o productos para las pruebas.")

        Partner = cls.env["res.partner"]
        cls.seller_a = Partner.create({"name": "Vendedor A prueba", "is_salesperson": True})
        cls.seller_b = Partner.create({"name": "Vendedor B prueba", "is_salesperson": True})
        customer_vals = {
            "is_company": True,
            "customer_rank": 1,
            "property_account_receivable_id": cls.receivable_account.id,
        }
        cls.customer_big = Partner.create(
            dict(
                customer_vals,
                name="CLIENTE GRANDE S.A.",
                commercial_name="TIENDA GRANDE",
                unique_id="99001",
            )
        )
        cls.branch_big = Partner.create(
            {
                "name": "Sucursal tienda grande",
                "parent_id": cls.customer_big.id,
                "type": "invoice",
                "property_account_receivable_id": cls.receivable_account.id,
            }
        )
        cls.customer_small = Partner.create(
            dict(customer_vals, name="CLIENTE PEQUEÑO S.A.", unique_id="99002")
        )

        # Enero 2027: factura con 10 % de descuento (bruto 1000, neto 900).
        cls.inv_jan = cls._create_move(
            "out_invoice", cls.branch_big, "2027-01-10", 10, 100.0,
            discount=10.0, taxes=cls.sale_tax, seller=cls.seller_a,
        )
        # Febrero 2027: factura sin descuento y nota de crédito.
        cls.inv_feb = cls._create_move(
            "out_invoice", cls.customer_big, "2027-02-05", 5, 100.0,
            taxes=cls.sale_tax, seller=cls.seller_a,
        )
        cls.nc_feb = cls._create_move(
            "out_refund", cls.customer_big, "2027-02-20", 1, 100.0,
            taxes=cls.sale_tax, seller=cls.seller_a,
        )
        # Cliente pequeño, otro vendedor.
        cls.inv_small = cls._create_move(
            "out_invoice", cls.customer_small, "2027-02-15", 1, 50.0,
            seller=cls.seller_b,
        )
        # Borrador: no debe aparecer.
        cls._create_move(
            "out_invoice", cls.customer_small, "2027-02-16", 99, 99.0,
            seller=cls.seller_b, post=False,
        )

    @classmethod
    def _create_move(cls, move_type, partner, date, quantity, price_unit,
                     discount=0.0, taxes=None, seller=None, post=True):
        move = cls.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_date": date,
                "date": date,
                "currency_id": cls.env.company.currency_id.id,
                "salesperson_id": seller.id if seller else False,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product.id,
                            "name": "Línea prueba",
                            "account_id": cls.income_account.id,
                            "quantity": quantity,
                            "price_unit": price_unit,
                            "discount": discount,
                            "tax_ids": [
                                Command.set((taxes or cls.env["account.tax"]).ids)
                            ],
                        }
                    )
                ],
            }
        )
        if seller:
            move.salesperson_id = seller
        if post:
            move.action_post()
        return move

    def _wizard(self, **values):
        values.setdefault("company_id", self.env.company.id)
        values.setdefault("date_from", "2027-01-01")
        values.setdefault("date_to", "2027-02-28")
        values.setdefault(
            "partner_ids",
            [Command.set((self.customer_big | self.customer_small).ids)],
        )
        return self.env["sng.facturacion.cliente.mensual.wizard"].create(values)

    def _row(self, data, partner):
        return next(r for r in data["rows"] if r["partner"] == partner)

    def test_months_and_values(self):
        data = self._wizard(date_from="2027-01-20", date_to="2027-02-03")._get_report_data()
        self.assertEqual(
            [m["label"] for m in data["months"]], ["ENERO 2027", "FEBRERO 2027"]
        )
        row = self._row(data, self.customer_big)
        self.assertEqual(row["code"], "99001")
        self.assertEqual(row["name"], "TIENDA GRANDE")

        jan = row["months"][(2027, 1)]
        self.assertAlmostEqual(jan["subtotal"], 1000.0)
        self.assertAlmostEqual(jan["discount"], 100.0)
        self.assertAlmostEqual(jan["tax"], self.inv_jan.amount_tax_signed)
        self.assertAlmostEqual(jan["credit_note"], 0.0)
        self.assertAlmostEqual(jan["vnai"], 900.0)
        self.assertAlmostEqual(jan["total"], self.inv_jan.amount_total_signed)

        feb = row["months"][(2027, 2)]
        self.assertAlmostEqual(feb["subtotal"], 500.0)
        self.assertAlmostEqual(feb["discount"], 0.0)
        # NC sin impuesto; su IVA rebaja la columna Impuesto.
        self.assertAlmostEqual(feb["credit_note"], 100.0)
        self.assertAlmostEqual(feb["vnai"], 400.0)
        self.assertAlmostEqual(
            feb["tax"], self.inv_feb.amount_tax_signed + self.nc_feb.amount_tax_signed
        )
        self.assertAlmostEqual(feb["total"], feb["vnai"] + feb["tax"])
        self.assertAlmostEqual(
            feb["total"],
            self.inv_feb.amount_total_signed + self.nc_feb.amount_total_signed,
        )
        self.assertAlmostEqual(row["period"]["total"], jan["total"] + feb["total"])

    def test_name_falls_back_and_draft_excluded(self):
        row = self._row(self._wizard()._get_report_data(), self.customer_small)
        self.assertEqual(row["name"], "CLIENTE PEQUEÑO S.A.")
        self.assertAlmostEqual(row["period"]["subtotal"], 50.0)

    def test_filters(self):
        data = self._wizard(salesperson_ids=[Command.set(self.seller_b.ids)])._get_report_data()
        self.assertEqual([r["partner"] for r in data["rows"]], [self.customer_small])

        data = self._wizard(partner_ids=[Command.set(self.branch_big.ids)])._get_report_data()
        self.assertEqual([r["partner"] for r in data["rows"]], [self.customer_big])

    def test_order_and_totals(self):
        data = self._wizard()._get_report_data()
        self.assertEqual(
            [r["partner"] for r in data["rows"]], [self.customer_big, self.customer_small]
        )
        for key in ("subtotal", "discount", "credit_note", "vnai", "tax", "total"):
            self.assertAlmostEqual(
                data["totals"]["period"][key],
                sum(r["period"][key] for r in data["rows"]),
            )
            self.assertAlmostEqual(
                data["totals"]["months"][(2027, 2)][key],
                sum(r["months"].get((2027, 2), {}).get(key, 0.0) for r in data["rows"]),
            )

    def test_validations(self):
        with self.assertRaises(ValidationError):
            self._wizard(date_from="2027-03-01", date_to="2027-01-31")
        with self.assertRaises(UserError):
            self._wizard(date_from="1999-01-01", date_to="1999-01-31").action_export_xlsx()

    def test_xlsx(self):
        wizard = self._wizard()
        self.assertEqual(wizard.action_export_xlsx()["report_type"], "xlsx")
        content, report_type = self.env["ir.actions.report"]._render(
            "sng_facturacion_cliente_mensual.facturacion_xlsx", wizard.ids, {}
        )
        self.assertEqual(report_type, "xlsx")
        sheet = load_workbook(BytesIO(content)).active
        self.assertEqual(sheet["A2"].value, "FACTURACIÓN POR CLIENTE MENSUAL DETALLADO")
        self.assertEqual(sheet["C4"].value, "ENERO 2027")
        self.assertEqual(sheet["I4"].value, "FEBRERO 2027")
        self.assertEqual(sheet["O4"].value, "TOTAL PERÍODO")
        self.assertEqual(
            [sheet.cell(5, c).value for c in range(1, 9)],
            ["Código cliente", "Nombre comercial", "Subtotal", "Descuento",
             "Notas de crédito", "VNAI", "Impuesto", "Total"],
        )
        self.assertEqual(sheet["A6"].value, "99001")
        self.assertEqual(sheet["B6"].value, "TIENDA GRANDE")
        self.assertEqual(sheet["A8"].value, "TOTAL GENERAL :")
        self.assertAlmostEqual(sheet["T8"].value, sheet["T6"].value + sheet["T7"].value)
        self.assertAlmostEqual(sheet["F6"].value, 900.0)
