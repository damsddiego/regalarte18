# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class SngCustomerProductReportLine(models.TransientModel):
    _name = "sng.customer.product.report.line"
    _description = "Línea de productos facturados por cliente"
    _order = "product_id, invoice_date, move_id, source_line_id"

    wizard_id = fields.Many2one(
        "sng.customer.product.report.wizard",
        string="Asistente",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        readonly=True,
        index=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda de compañía",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente comercial",
        required=True,
        readonly=True,
        index=True,
    )
    invoice_partner_id = fields.Many2one(
        "res.partner",
        string="Contacto facturado",
        required=True,
        readonly=True,
        index=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Documento",
        required=True,
        readonly=True,
        index=True,
    )
    source_line_id = fields.Many2one(
        "account.move.line",
        string="Línea contable",
        required=True,
        readonly=True,
        index=True,
    )
    invoice_date = fields.Date(
        string="Fecha",
        required=True,
        readonly=True,
        index=True,
    )
    document_number = fields.Char(
        string="Número",
        required=True,
        readonly=True,
        index=True,
    )
    document_type = fields.Selection(
        [
            ("out_invoice", "Factura"),
            ("out_refund", "Nota de crédito"),
        ],
        string="Tipo",
        required=True,
        readonly=True,
        index=True,
    )
    is_credit_note = fields.Boolean(
        string="Es nota de crédito",
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
        index=True,
    )
    product_code = fields.Char(
        string="Código",
        readonly=True,
        index=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UdM facturada",
        required=True,
        readonly=True,
    )
    base_uom_id = fields.Many2one(
        "uom.uom",
        string="UdM base",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        required=True,
        readonly=True,
    )
    quantity = fields.Float(
        string="Cantidad",
        digits="Product Unit of Measure",
        readonly=True,
    )
    base_quantity = fields.Float(
        string="Cantidad base",
        digits="Product Unit of Measure",
        readonly=True,
    )
    price_unit = fields.Monetary(
        string="Precio unitario",
        currency_field="currency_id",
        readonly=True,
    )
    discount = fields.Float(
        string="Descuento (%)",
        digits="Discount",
        readonly=True,
    )
    subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        readonly=True,
    )
    tax_amount = fields.Monetary(
        string="IVA",
        currency_field="currency_id",
        readonly=True,
    )
    total = fields.Monetary(
        string="Total",
        currency_field="currency_id",
        readonly=True,
    )
    subtotal_company = fields.Monetary(
        string="Subtotal CRC",
        currency_field="company_currency_id",
        readonly=True,
    )
    tax_amount_company = fields.Monetary(
        string="IVA CRC",
        currency_field="company_currency_id",
        readonly=True,
    )
    total_company = fields.Monetary(
        string="Total CRC",
        currency_field="company_currency_id",
        readonly=True,
    )

    def _get_context_wizard(self):
        wizard_id = self.env.context.get("customer_product_report_wizard_id")
        if not wizard_id and self:
            wizard_id = self[0].wizard_id.id
        wizard = self.env["sng.customer.product.report.wizard"].browse(
            wizard_id
        ).exists()
        if not wizard:
            raise UserError(_("No se encontró el asistente asociado al reporte."))
        return wizard

    def action_open_invoice(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.document_number,
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_filters(self):
        return self._get_context_wizard().action_open_wizard()

    def action_print_pdf(self):
        return self._get_context_wizard().action_print_pdf(rebuild=False)

    def action_export_xlsx(self):
        return self._get_context_wizard().action_export_xlsx(rebuild=False)
