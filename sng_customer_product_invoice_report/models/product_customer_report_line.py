# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class SngProductCustomerReportLine(models.TransientModel):
    _name = "sng.product.customer.report.line"
    _inherit = "sng.customer.product.report.line"
    _description = "Línea de clientes por producto facturado"
    _order = "product_id, partner_id, invoice_date, move_id, source_line_id"

    wizard_id = fields.Many2one(
        "sng.product.customer.report.wizard",
        string="Asistente",
        required=True,
        ondelete="cascade",
        index=True,
    )

    def _get_context_wizard(self):
        wizard_id = self.env.context.get("product_customer_report_wizard_id")
        if not wizard_id and self:
            wizard_id = self[0].wizard_id.id
        wizard = self.env["sng.product.customer.report.wizard"].browse(
            wizard_id
        ).exists()
        if not wizard:
            raise UserError(_("No se encontró el asistente asociado al reporte."))
        return wizard

    def action_open_filters(self):
        return self._get_context_wizard().action_open_wizard()

    def action_print_pdf(self):
        return self._get_context_wizard().action_print_pdf(rebuild=False)

    def action_export_xlsx(self):
        return self._get_context_wizard().action_export_xlsx(rebuild=False)
