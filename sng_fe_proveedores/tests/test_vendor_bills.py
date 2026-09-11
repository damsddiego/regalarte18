# -*- coding: utf-8 -*-
import base64
from datetime import date, timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sng_fe_proveedores")
class TestVendorBills(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        base_journal = env["account.journal"].search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", cls.company.id),
                ("default_account_id", "!=", False),
            ],
            limit=1,
        )
        cls.expense_account = base_journal.default_account_id
        cls.fec_sequence = env["ir.sequence"].create(
            {"name": "Test FEC", "code": "test.fec", "padding": 10, "company_id": cls.company.id}
        )
        cls.journal_fec = env["account.journal"].create(
            {
                "name": "Test FEC",
                "code": "TFEC",
                "type": "purchase",
                "company_id": cls.company.id,
                "FEC_sequence_id": cls.fec_sequence.id,
                "default_account_id": cls.expense_account.id,
            }
        )
        cls.journal_plain = env["account.journal"].create(
            {
                "name": "Test compras sin FE",
                "code": "TNOF",
                "type": "purchase",
                "company_id": cls.company.id,
                "default_account_id": cls.expense_account.id,
            }
        )
        cls.da_sequence = env["ir.sequence"].search([("code", "=", "sequence.DA")], limit=1)
        ident_juridica = env["identification.type"].search([("code", "=", "02")], limit=1)
        activity = env["economic.activity"].search([], limit=1)
        payment_method = env["payment.methods"].search([], limit=1)
        payable = env["account.account"].search(
            [
                ("company_ids", "in", cls.company.id),
                ("account_type", "=", "liability_payable"),
                ("deprecated", "=", False),
            ],
            limit=1,
        )
        cls.partner_cr = env["res.partner"].create(
            {
                "name": "Proveedor CR Test",
                "country_id": env.ref("base.cr").id,
                "vat": "3101123456",
                "identification_id": ident_juridica.id,
                "activity_id": activity.id,
                "payment_methods_id": payment_method.id,
                "property_account_payable_id": payable.id,
                "supplier_rank": 1,
            }
        )
        cls.partner_sin_cedula = env["res.partner"].create(
            {
                "name": "Proveedor sin cédula",
                "country_id": env.ref("base.cr").id,
                "payment_methods_id": payment_method.id,
                "property_account_payable_id": payable.id,
                "supplier_rank": 1,
            }
        )
        cls.activity = activity

    def _bill(self, journal, partner=None, move_type="in_invoice", **extra):
        vals = {
            "move_type": move_type,
            "journal_id": journal.id,
            "partner_id": (partner or self.partner_cr).id,
            "invoice_date": date.today(),
            "economic_activity_id": self.activity.id,
            "invoice_line_ids": [
                Command.create(
                    {
                        "name": "Servicio de prueba",
                        "quantity": 1,
                        "price_unit": 1000,
                        "account_id": self.expense_account.id,
                        "tax_ids": [Command.clear()],
                    }
                )
            ],
        }
        vals.update(extra)
        return self.env["account.move"].create(vals)

    def test_plain_journal_bill_is_disabled_and_keeps_standard_name(self):
        da_next = self.da_sequence.number_next_actual if self.da_sequence else None
        bill = self._bill(self.journal_plain)
        self.assertEqual(bill.tipo_documento, "disabled")
        bill.action_post()
        self.assertEqual(bill.state, "posted")
        self.assertEqual(bill.tipo_documento, "disabled")
        self.assertFalse(bill.sequence)
        self.assertFalse(bill.number_electronic)
        self.assertTrue(bill.name.startswith("TNOF/"), bill.name)
        if self.da_sequence:
            self.assertEqual(self.da_sequence.number_next_actual, da_next)

    def test_default_fe_from_form_is_corrected(self):
        # El campo tipo_documento tiene default "FE"; el formulario lo envía.
        bill = self._bill(self.journal_plain, tipo_documento="FE")
        self.assertEqual(bill.tipo_documento, "disabled")

    def test_fec_journal_bill_is_fec_and_named_by_consecutive(self):
        bill = self._bill(self.journal_fec)
        self.assertEqual(bill.tipo_documento, "FEC")
        bill.action_post()
        self.assertEqual(bill.tipo_documento, "FEC")
        self.assertTrue(bill.sequence)
        self.assertEqual(bill.name, bill.sequence)
        self.assertEqual(len(bill.number_electronic), 50)
        self.assertEqual(bill.sequence[8:10], "08")  # tipo FEC en el consecutivo

    def test_fec_journal_with_supplier_xml_is_blocked(self):
        xml = base64.b64encode(b"<FacturaElectronica/>")
        bill = self._bill(self.journal_fec, xml_supplier_approval=xml)
        self.assertEqual(bill.tipo_documento, "disabled")
        with self.assertRaises(UserError):
            bill.action_post()

    def test_fec_missing_partner_data_raises_clear_error(self):
        bill = self._bill(self.journal_fec, partner=self.partner_sin_cedula)
        self.assertEqual(bill.tipo_documento, "FEC")
        with self.assertRaisesRegex(UserError, "cédula del proveedor"):
            bill.action_post()

    def test_journal_change_resyncs_tipo(self):
        bill = self._bill(self.journal_plain)
        self.assertEqual(bill.tipo_documento, "disabled")
        # Misma escritura que hace la automatización "Régimen Simplificado FEC".
        bill.write({"journal_id": self.journal_fec.id, "name": "/"})
        self.assertEqual(bill.tipo_documento, "FEC")
        bill.write({"journal_id": self.journal_plain.id})
        self.assertEqual(bill.tipo_documento, "disabled")

    def test_refund_in_fec_journal_is_disabled(self):
        refund = self._bill(self.journal_fec, move_type="in_refund")
        self.assertEqual(refund.tipo_documento, "disabled")
        refund.action_post()
        self.assertEqual(refund.state, "posted")
        self.assertFalse(refund.sequence)

    def test_batch_post_of_vendor_bills(self):
        bills = self._bill(self.journal_plain) | self._bill(self.journal_plain)
        bills.action_post()
        self.assertEqual(set(bills.mapped("state")), {"posted"})
        self.assertEqual(len(set(bills.mapped("name"))), 2)

    def _post_legacy_named(self, journal, name, day):
        """Publica una factura y la renombra como los nombres heredados
        (DA########## o consecutivo FEC de 20 dígitos) que hoy existen en FACTU."""
        bill = self._bill(journal, invoice_date=day, date=day)
        bill.action_post()
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE account_move SET name=%s WHERE id=%s", (name, bill.id)
        )
        bill.invalidate_recordset(["name", "sequence_prefix", "sequence_number"])
        bill._compute_split_sequence()
        self.env.flush_all()
        # Un rename por ORM limpia esta caché transaccional; por SQL hay que hacerlo a mano.
        bill._get_sequence_cache().clear()
        self.assertEqual(bill.name, name)
        return bill

    def test_legacy_names_are_ignored_for_standard_numbering(self):
        today = date.today()
        self._post_legacy_named(self.journal_plain, "00100001080000003040", today)
        self._post_legacy_named(self.journal_plain, "DA0000001300", today)
        bill = self._bill(self.journal_plain, invoice_date=today, date=today)
        bill.action_post()
        self.assertEqual(bill.name, "TNOF/%s/%02d/0001" % (today.year, today.month))
        bill2 = self._bill(self.journal_plain, invoice_date=today, date=today)
        bill2.action_post()
        self.assertEqual(bill2.name, "TNOF/%s/%02d/0002" % (today.year, today.month))

    def test_backdated_bill_gets_its_own_month(self):
        today = date.today()
        self._post_legacy_named(self.journal_plain, "DA0000001301", today)
        current = self._bill(self.journal_plain, invoice_date=today, date=today)
        current.action_post()
        self.assertEqual(current.name, "TNOF/%s/%02d/0001" % (today.year, today.month))
        prev = today.replace(day=1) - timedelta(days=1)
        old = self._bill(self.journal_plain, invoice_date=prev, date=prev)
        old.action_post()
        # Con fecha de bloqueo contable Odoo puede mover la fecha; se valida
        # contra la fecha real del asiento.
        if (old.date.year, old.date.month) == (today.year, today.month):
            self.skipTest("La fecha de bloqueo impide publicar en el mes anterior")
        self.assertEqual(old.name, "TNOF/%s/%02d/0001" % (old.date.year, old.date.month))
        nxt = self._bill(self.journal_plain, invoice_date=today, date=today)
        nxt.action_post()
        self.assertEqual(nxt.name, "TNOF/%s/%02d/0002" % (today.year, today.month))

    def test_refund_uses_r_prefix(self):
        today = date.today()
        self._post_legacy_named(self.journal_plain, "DA0000001302", today)
        refund = self._bill(self.journal_plain, move_type="in_refund", invoice_date=today, date=today)
        refund.action_post()
        self.assertEqual(refund.name, "RTNOF/%s/%02d/0001" % (today.year, today.month))

    def test_customer_invoice_untouched(self):
        income = self.env["account.account"].search(
            [("company_ids", "in", self.company.id), ("account_type", "=", "income")],
            limit=1,
        )
        inv = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_cr.id,
                "invoice_line_ids": [
                    Command.create(
                        {"name": "x", "quantity": 1, "price_unit": 10, "account_id": income.id}
                    )
                ],
            }
        )
        self.assertEqual(inv.tipo_documento, "FE")
