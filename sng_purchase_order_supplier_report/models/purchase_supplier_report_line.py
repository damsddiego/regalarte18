# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class SngPurchaseSupplierReportLine(models.TransientModel):
    _name = "sng.purchase.supplier.report.line"
    _description = "Línea de órdenes de compra por proveedor"
    _order = (
        "supplier_id, product_id, confirmation_date, order_id, "
        "source_line_id"
    )

    wizard_id = fields.Many2one(
        "sng.purchase.supplier.report.wizard",
        string="Asistente",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="wizard_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        related="wizard_id.user_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda de compañía",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        required=True,
        readonly=True,
        index=True,
    )
    order_id = fields.Many2one(
        "purchase.order",
        string="Orden de compra",
        required=True,
        readonly=True,
        index=True,
    )
    source_line_id = fields.Many2one(
        "purchase.order.line",
        string="Línea de origen",
        required=True,
        readonly=True,
        index=True,
    )
    confirmation_date = fields.Datetime(
        string="Fecha de confirmación",
        required=True,
        readonly=True,
        index=True,
    )
    planned_date = fields.Datetime(
        string="Llegada prevista",
        readonly=True,
        index=True,
    )
    vendor_reference = fields.Char(
        string="Referencia proveedor",
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
        string="UdM de compra",
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
        string="Moneda OC",
        required=True,
        readonly=True,
    )
    qty_ordered = fields.Float(
        string="Cantidad ordenada",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_received = fields.Float(
        string="Cantidad recibida",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_pending = fields.Float(
        string="Cantidad pendiente",
        digits="Product Unit of Measure",
        readonly=True,
    )
    base_qty_ordered = fields.Float(
        string="Ordenada en UdM base",
        digits="Product Unit of Measure",
        readonly=True,
    )
    base_qty_received = fields.Float(
        string="Recibida en UdM base",
        digits="Product Unit of Measure",
        readonly=True,
    )
    base_qty_pending = fields.Float(
        string="Pendiente en UdM base",
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
        string="Subtotal OC",
        currency_field="currency_id",
        readonly=True,
    )
    tax_amount = fields.Monetary(
        string="Impuestos OC",
        currency_field="currency_id",
        readonly=True,
    )
    total = fields.Monetary(
        string="Total OC",
        currency_field="currency_id",
        readonly=True,
    )
    pending_subtotal = fields.Monetary(
        string="Subtotal pendiente",
        currency_field="currency_id",
        readonly=True,
    )
    pending_tax = fields.Monetary(
        string="Impuestos pendientes",
        currency_field="currency_id",
        readonly=True,
    )
    pending_total = fields.Monetary(
        string="Total pendiente",
        currency_field="currency_id",
        readonly=True,
    )
    subtotal_company = fields.Monetary(
        string="Subtotal compañía",
        currency_field="company_currency_id",
        readonly=True,
    )
    tax_company = fields.Monetary(
        string="Impuestos compañía",
        currency_field="company_currency_id",
        readonly=True,
    )
    total_company = fields.Monetary(
        string="Total compañía",
        currency_field="company_currency_id",
        readonly=True,
    )
    pending_subtotal_company = fields.Monetary(
        string="Subtotal pendiente compañía",
        currency_field="company_currency_id",
        readonly=True,
    )
    pending_tax_company = fields.Monetary(
        string="Impuestos pendientes compañía",
        currency_field="company_currency_id",
        readonly=True,
    )
    pending_total_company = fields.Monetary(
        string="Total pendiente compañía",
        currency_field="company_currency_id",
        readonly=True,
    )
    reception_state = fields.Selection(
        [
            ("transit", "En tránsito"),
            ("received", "Recibida"),
        ],
        string="Estado de recepción",
        required=True,
        readonly=True,
        index=True,
    )

    def _get_context_wizard(self):
        wizard_id = self.env.context.get("purchase_supplier_report_wizard_id")
        if not wizard_id and self:
            wizard_id = self[0].wizard_id.id
        wizard = self.env["sng.purchase.supplier.report.wizard"].browse(
            wizard_id
        ).exists()
        if not wizard:
            raise UserError(_("No se encontró el asistente asociado al reporte."))
        return wizard

    def action_open_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.order_id.display_name,
            "res_model": "purchase.order",
            "res_id": self.order_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_filters(self):
        return self._get_context_wizard().action_open_wizard()

    def action_print_pdf(self):
        return self._get_context_wizard().action_print_pdf(rebuild=False)

    def action_export_xlsx(self):
        return self._get_context_wizard().action_export_xlsx(rebuild=False)

