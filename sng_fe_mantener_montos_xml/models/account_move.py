# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _sng_mark_xml_lines(self):
        """Marca como provenientes del XML las líneas de producto de facturas con XML de proveedor."""
        for move in self.filtered("xml_supplier_approval"):
            lines = move.invoice_line_ids.filtered(
                lambda line: line.display_type == "product" and not line.fe_xml_line
            )
            if lines:
                lines.write({"fe_xml_line": True})

    def load_xml_data(self):
        # Ruta manual (carga del XML desde la factura o al enviar el mensaje receptor).
        result = super().load_xml_data()
        self._sng_mark_xml_lines()
        return result
