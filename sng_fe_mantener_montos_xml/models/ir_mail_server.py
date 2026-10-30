# -*- coding: utf-8 -*-
from odoo import models


class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    def create_invoice_with_attamecth(self, msg, company_id):
        # Ruta del correo: cr_import_vendor_bills crea la factura y sus líneas desde el XML.
        invoice = super().create_invoice_with_attamecth(msg, company_id)
        if invoice and getattr(invoice, "_name", None) == "account.move":
            invoice._sng_mark_xml_lines()
        return invoice
