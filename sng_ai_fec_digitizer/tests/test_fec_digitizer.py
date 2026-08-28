# -*- coding: utf-8 -*-
import base64
import io

from PyPDF2 import PdfWriter

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFecDigitizer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=500)
        output = io.BytesIO()
        writer.write(output)
        cls.batch = cls.env["sng.ai.fec.batch"].create({
            "name": "Prueba", "pdf_filename": "prueba.pdf",
            "pdf_data": base64.b64encode(output.getvalue()), "page_count": 1,
        })

    def test_ai_payload_is_converted_to_proposal_values(self):
        values = self.env["sng.ai.fec.proposal"]._values_from_ai({
            "pages": [1], "supplier_name": "Soda Prueba", "supplier_vat": "1-234-567890",
            "reference": "101", "invoice_date": "2026-08-01", "currency": "CRC",
            "subtotal": 5000, "tax_total": 0, "total": 5000,
            "confidence": {"total": 0.99, "supplier_vat": 0.95},
            "lines": [{"description": "Servicio", "quantity": 1, "unit_price": 5000,
                       "tax_rate": 0, "total": 5000}],
        }, 1)
        proposal = self.env["sng.ai.fec.proposal"].create(dict(values, batch_id=self.batch.id))
        self.assertEqual(proposal.page_numbers, "1")
        self.assertEqual(proposal.reference, "101")
        self.assertEqual(proposal.total, 5000)
        self.assertEqual(len(proposal.line_ids), 1)
        self.assertGreater(proposal.confidence, 0.90)

    def test_batch_default_state_does_not_leak_to_proposal(self):
        proposal_model = self.env["sng.ai.fec.proposal"].with_context(default_state="uploaded")
        values = proposal_model._values_from_ai({
            "pages": [1], "supplier_name": "Soda Prueba", "reference": "CTX-1",
            "invoice_date": "2026-08-01", "currency": "CRC", "total": 1000,
            "lines": [{"description": "Servicio", "quantity": 1, "unit_price": 1000, "total": 1000}],
        }, 1)
        proposal = proposal_model.create(dict(values, batch_id=self.batch.id))
        self.assertEqual(proposal.state, "review")

    def test_invalid_page_group_is_rejected(self):
        with self.assertRaises(UserError):
            self.env["sng.ai.fec.proposal"]._values_from_ai({"pages": [2]}, 1)

    def test_unknown_partner_cannot_create_invoice(self):
        proposal = self.env["sng.ai.fec.proposal"].create({
            "batch_id": self.batch.id, "page_numbers": "1", "supplier_name": "Desconocido",
            "reference": "X-1", "invoice_date": "2026-08-01", "total": 1000,
            "line_ids": [Command.create({"description": "Servicio", "quantity": 1, "unit_price": 1000})],
        })
        with self.assertRaises(UserError):
            proposal.action_create_invoice()

    def test_queue_requires_privacy_consent(self):
        with self.assertRaises(UserError):
            self.batch.action_queue()

    def test_duplicate_proposal_is_detected(self):
        partner = self.env["res.partner"].create({"name": "Proveedor prueba", "vat": "123456789"})
        first = self.env["sng.ai.fec.proposal"].create({
            "batch_id": self.batch.id, "page_numbers": "1", "partner_id": partner.id,
            "reference": "DUP-1", "invoice_date": "2026-08-01", "total": 1000,
        })
        second = self.env["sng.ai.fec.proposal"].create({
            "batch_id": self.batch.id, "page_numbers": "1", "partner_id": partner.id,
            "reference": "DUP-1", "invoice_date": "2026-08-01", "total": 1000,
        })
        duplicate, move = second._duplicate_matches()
        self.assertEqual(duplicate, first)
        self.assertFalse(move)
