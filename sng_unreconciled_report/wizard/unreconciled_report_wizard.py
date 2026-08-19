# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime

from odoo import fields, models, api
from odoo.exceptions import UserError

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class SngUnreconciledReportInvoiceLine(models.TransientModel):
    _name = "sng.unreconciled.report.invoice.line"
    _description = "Línea de factura pendiente"
    _order = "invoice_date_due, partner_name"

    wizard_id = fields.Many2one("sng.unreconciled.report.wizard", ondelete="cascade")
    move_id = fields.Many2one("account.move", string="Factura", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    partner_name = fields.Char(string="Nombre Cliente", readonly=True)
    invoice_name = fields.Char(string="Número", readonly=True)
    invoice_date = fields.Date(string="Fecha Factura", readonly=True)
    invoice_date_due = fields.Date(string="Vencimiento", readonly=True)
    amount_total = fields.Float(string="Total", digits=(16, 2), readonly=True)
    amount_residual = fields.Float(string="Pendiente", digits=(16, 2), readonly=True)
    currency_name = fields.Char(string="Moneda", readonly=True)
    payment_state = fields.Char(string="Estado de Pago", readonly=True)
    days_overdue = fields.Integer(
        string="Días Vencida",
        compute="_compute_days_overdue",
        readonly=True,
    )

    @api.depends("invoice_date_due")
    def _compute_days_overdue(self):
        today = fields.Date.context_today(self)
        for line in self:
            if line.invoice_date_due and line.invoice_date_due < today:
                line.days_overdue = (today - line.invoice_date_due).days
            else:
                line.days_overdue = 0

    def action_open_invoice(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError("No se encontró la factura asociada a esta línea.")
        return {
            "type": "ir.actions.act_window",
            "name": self.invoice_name or "Factura",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
            "target": "current",
        }


class SngUnreconciledReportPaymentLine(models.TransientModel):
    _name = "sng.unreconciled.report.payment.line"
    _description = "Línea de pago no conciliado"
    _order = "date, partner_name"

    wizard_id = fields.Many2one("sng.unreconciled.report.wizard", ondelete="cascade")
    payment_id = fields.Many2one("account.payment", string="Pago", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente/Proveedor", readonly=True)
    partner_name = fields.Char(string="Nombre", readonly=True)
    payment_name = fields.Char(string="Número Pago", readonly=True)
    date = fields.Date(string="Fecha", readonly=True)
    amount = fields.Float(string="Monto", digits=(16, 2), readonly=True)
    currency_name = fields.Char(string="Moneda", readonly=True)
    journal_name = fields.Char(string="Diario", readonly=True)
    payment_method_name = fields.Char(string="Método de Pago", readonly=True)
    applicable_invoice_count = fields.Integer(string="Facturas Aplicables", readonly=True)
    applicable_invoice_names = fields.Char(string="Facturas a Aplicar", readonly=True)
    applicable_invoice_residual_summary = fields.Char(
        string="Pendiente en Facturas",
        readonly=True,
    )

    @api.model
    def _get_applicable_invoices(self, payment):
        partner = payment.partner_id.commercial_partner_id or payment.partner_id
        move_types = (
            ["out_invoice", "out_refund"]
            if payment.payment_type == "inbound"
            else ["in_invoice", "in_refund"]
        )
        return self.env["account.move"].search(
            [
                ("move_type", "in", move_types),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial", "in_payment"]),
                ("commercial_partner_id", "=", partner.id),
            ],
            order="invoice_date_due, name",
        )

    @api.model
    def _format_applicable_invoice_names(self, invoices, limit=3):
        invoice_labels = [
            "%s (%s %s)" % (
                inv.name or "Sin número",
                inv.currency_id.name or "",
                format(inv.amount_residual, ",.2f"),
            )
            for inv in invoices[:limit]
        ]
        remaining = len(invoices) - len(invoice_labels)
        if remaining > 0:
            invoice_labels.append("+%s más" % remaining)
        return "; ".join(invoice_labels) or "Sin facturas pendientes"

    @api.model
    def _format_applicable_invoice_residual(self, invoices):
        totals_by_currency = {}
        for inv in invoices:
            currency = inv.currency_id.name or "Sin moneda"
            totals_by_currency[currency] = totals_by_currency.get(currency, 0.0) + inv.amount_residual
        if not totals_by_currency:
            return "0.00"
        return " / ".join(
            "%s %s" % (currency, format(amount, ",.2f"))
            for currency, amount in sorted(totals_by_currency.items())
        )

    def action_open_payment(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError("No se encontró el pago asociado a esta línea.")
        return {
            "type": "ir.actions.act_window",
            "name": self.payment_name or "Pago",
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.payment_id.id,
            "target": "current",
        }

    def action_open_reconcile(self):
        self.ensure_one()
        payment = self.payment_id
        partner = payment.partner_id.commercial_partner_id or payment.partner_id

        invoices = self._get_applicable_invoices(payment)
        if not invoices:
            raise UserError("No hay facturas pendientes para este cliente/proveedor.")

        account_types = ("asset_receivable", "liability_payable")
        payment_ml = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in account_types
        )
        amount_available = abs(sum(payment_ml.mapped("amount_residual")))

        reconcile_wiz = self.env["sng.reconcile.payment.wizard"].create({
            "parent_wizard_id": self.wizard_id.id,
            "payment_id": payment.id,
            "payment_name": payment.name or "",
            "partner_id": partner.id,
            "amount": payment.amount,
            "amount_available": amount_available,
            "currency_id": payment.currency_id.id,
            "date": payment.date,
            "journal_name": payment.journal_id.name or "",
            "invoice_line_ids": [
                (0, 0, {
                    "move_id": inv.id,
                    "invoice_name": inv.name or "",
                    "invoice_date": inv.invoice_date,
                    "invoice_date_due": inv.invoice_date_due,
                    "amount_total": inv.amount_total,
                    "amount_residual": inv.amount_residual,
                    "currency_name": inv.currency_id.name or "",
                })
                for inv in invoices
            ],
        })
        return {
            "type": "ir.actions.act_window",
            "name": "Conciliar Pago",
            "res_model": "sng.reconcile.payment.wizard",
            "view_mode": "form",
            "res_id": reconcile_wiz.id,
            "target": "new",
        }


class SngUnreconciledReportWizard(models.TransientModel):
    _name = "sng.unreconciled.report.wizard"
    _description = "Wizard Reporte Facturas y Pagos No Conciliados"

    date_from = fields.Date(string="Desde")
    date_to = fields.Date(string="Hasta")
    partner_ids = fields.Many2many(
        "res.partner",
        "sng_unreconciled_report_wizard_partner_rel",
        "wizard_id",
        "partner_id",
        string="Clientes",
        domain=["|", ("customer_rank", ">", 0), ("supplier_rank", ">", 0)],
    )
    invoice_type = fields.Selection(
        [
            ("out", "Solo Cliente (CxC)"),
            ("in", "Solo Proveedor (CxP)"),
            ("all", "Ambos"),
        ],
        string="Tipo de Facturas",
        default="out",
        required=True,
    )
    invoice_line_ids = fields.One2many(
        "sng.unreconciled.report.invoice.line",
        "wizard_id",
        string="Facturas Pendientes",
        readonly=True,
    )
    payment_line_ids = fields.One2many(
        "sng.unreconciled.report.payment.line",
        "wizard_id",
        string="Pagos No Conciliados",
        readonly=True,
    )
    invoice_line_count = fields.Integer(string="Cantidad Facturas", compute="_compute_counts")
    payment_line_count = fields.Integer(string="Cantidad Pagos", compute="_compute_counts")
    invoice_total_summary = fields.Char(
        string="Total Facturado",
        compute="_compute_amount_summaries",
    )
    invoice_residual_summary = fields.Char(
        string="Total Pendiente",
        compute="_compute_amount_summaries",
    )
    payment_total_summary = fields.Char(
        string="Total Pagos",
        compute="_compute_amount_summaries",
    )
    report_file = fields.Binary(string="Archivo Excel", readonly=True)
    report_filename = fields.Char(string="Nombre archivo", readonly=True)

    @api.depends("invoice_line_ids", "payment_line_ids")
    def _compute_counts(self):
        for wiz in self:
            wiz.invoice_line_count = len(wiz.invoice_line_ids)
            wiz.payment_line_count = len(wiz.payment_line_ids)

    def _format_amount_summary(self, lines, amount_field):
        totals_by_currency = {}
        for line in lines:
            currency = line.currency_name or "Sin moneda"
            totals_by_currency[currency] = totals_by_currency.get(currency, 0.0) + line[amount_field]
        if not totals_by_currency:
            return "0.00"
        return " / ".join(
            "%s %s" % (currency, format(amount, ",.2f"))
            for currency, amount in sorted(totals_by_currency.items())
        )

    @api.depends(
        "invoice_line_ids.amount_total",
        "invoice_line_ids.amount_residual",
        "invoice_line_ids.currency_name",
        "payment_line_ids.amount",
        "payment_line_ids.currency_name",
    )
    def _compute_amount_summaries(self):
        for wiz in self:
            wiz.invoice_total_summary = wiz._format_amount_summary(
                wiz.invoice_line_ids, "amount_total"
            )
            wiz.invoice_residual_summary = wiz._format_amount_summary(
                wiz.invoice_line_ids, "amount_residual"
            )
            wiz.payment_total_summary = wiz._format_amount_summary(
                wiz.payment_line_ids, "amount"
            )

    def _get_invoice_types(self):
        self.ensure_one()
        if self.invoice_type == "out":
            return ["out_invoice", "out_refund"]
        elif self.invoice_type == "in":
            return ["in_invoice", "in_refund"]
        return ["out_invoice", "out_refund", "in_invoice", "in_refund"]

    def _get_payment_types(self):
        self.ensure_one()
        if self.invoice_type == "out":
            return ["inbound"]
        elif self.invoice_type == "in":
            return ["outbound"]
        return ["inbound", "outbound"]

    def _do_generate(self):
        self.ensure_one()
        self.invoice_line_ids.unlink()
        self.payment_line_ids.unlink()

        # --- Facturas no pagadas ---
        invoice_domain = [
            ("move_type", "in", self._get_invoice_types()),
            ("state", "=", "posted"),
            ("payment_state", "in", ["not_paid", "partial", "in_payment"]),
        ]
        if self.date_from:
            invoice_domain.append(("invoice_date", ">=", self.date_from))
        if self.date_to:
            invoice_domain.append(("invoice_date", "<=", self.date_to))
        if self.partner_ids:
            invoice_domain.append(("commercial_partner_id", "in", self.partner_ids.ids))

        invoices = self.env["account.move"].search(invoice_domain)
        invoice_commands = [(5, 0, 0)]
        for inv in invoices:
            invoice_commands.append((0, 0, {
                "move_id": inv.id,
                "partner_id": inv.commercial_partner_id.id,
                "partner_name": inv.commercial_partner_id.name or "",
                "invoice_name": inv.name or "",
                "invoice_date": inv.invoice_date,
                "invoice_date_due": inv.invoice_date_due,
                "amount_total": inv.amount_total,
                "amount_residual": inv.amount_residual,
                "currency_name": inv.currency_id.name or "",
                "payment_state": dict(inv._fields["payment_state"].selection).get(inv.payment_state, inv.payment_state),
            }))

        # --- Pagos confirmados no conciliados ---
        # state 'in_process': move publicado, línea de liquidez aún no conciliada con extracto
        # state 'paid': línea de liquidez conciliada pero el contraparte (CxC/CxP) puede seguir abierto
        payment_domain = [
            ("payment_type", "in", self._get_payment_types()),
            ("state", "in", ["in_process", "paid"]),
            ("is_reconciled", "=", False),
        ]
        if self.date_from:
            payment_domain.append(("date", ">=", self.date_from))
        if self.date_to:
            payment_domain.append(("date", "<=", self.date_to))
        if self.partner_ids:
            payment_domain.append(("commercial_partner_id", "in", self.partner_ids.ids))

        payments = self.env["account.payment"].search(payment_domain)
        payment_line_model = self.env["sng.unreconciled.report.payment.line"]
        payment_commands = [(5, 0, 0)]
        for pay in payments:
            applicable_invoices = payment_line_model._get_applicable_invoices(pay)
            payment_commands.append((0, 0, {
                "payment_id": pay.id,
                "partner_id": pay.partner_id.id,
                "partner_name": pay.partner_id.name or "",
                "payment_name": pay.name or "",
                "date": pay.date,
                "amount": pay.amount,
                "currency_name": pay.currency_id.name or "",
                "journal_name": pay.journal_id.name or "",
                "payment_method_name": pay.payment_method_line_id.name if pay.payment_method_line_id else "",
                "applicable_invoice_count": len(applicable_invoices),
                "applicable_invoice_names": payment_line_model._format_applicable_invoice_names(applicable_invoices),
                "applicable_invoice_residual_summary": payment_line_model._format_applicable_invoice_residual(applicable_invoices),
            }))

        self.write({
            "invoice_line_ids": invoice_commands,
            "payment_line_ids": payment_commands,
        })

    def action_generate(self):
        self.ensure_one()
        self._do_generate()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_download(self):
        self.ensure_one()
        if not self.invoice_line_ids and not self.payment_line_ids:
            raise UserError("Primero debe generar el reporte antes de descargar.")

        excel = self._generate_excel()
        filename = "facturas_pagos_no_conciliados_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self.write({
            "report_file": base64.b64encode(excel),
            "report_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=report_file&filename=%s&download=true"
                   % (self._name, self.id, filename),
            "target": "self",
        }

    def _generate_excel(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True, "remove_timezone": True})

        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#4472C4", "color": "white",
            "align": "center", "valign": "vcenter", "border": 1,
        })
        text_fmt = workbook.add_format({"align": "left", "valign": "vcenter", "border": 1})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy", "align": "center", "valign": "vcenter", "border": 1})
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "align": "right", "valign": "vcenter", "border": 1})

        # Hoja 1: Facturas Pendientes
        ws1 = workbook.add_worksheet("Facturas Pendientes")
        ws1.freeze_panes(1, 0)

        headers1 = ["Cliente", "Número Factura", "Fecha", "Vencimiento", "Total", "Pendiente", "Moneda", "Estado de Pago"]
        widths1 = [35, 20, 14, 14, 18, 18, 12, 18]
        for col, (header, width) in enumerate(zip(headers1, widths1)):
            ws1.write(0, col, header, header_fmt)
            ws1.set_column(col, col, width)

        for row_idx, line in enumerate(self.invoice_line_ids, start=1):
            ws1.write(row_idx, 0, line.partner_name or "", text_fmt)
            ws1.write(row_idx, 1, line.invoice_name or "", text_fmt)
            ws1.write(row_idx, 2, line.invoice_date or "", date_fmt)
            ws1.write(row_idx, 3, line.invoice_date_due or "", date_fmt)
            ws1.write(row_idx, 4, line.amount_total, money_fmt)
            ws1.write(row_idx, 5, line.amount_residual, money_fmt)
            ws1.write(row_idx, 6, line.currency_name or "", text_fmt)
            ws1.write(row_idx, 7, line.payment_state or "", text_fmt)

        # Hoja 2: Pagos No Conciliados
        ws2 = workbook.add_worksheet("Pagos No Conciliados")
        ws2.freeze_panes(1, 0)

        headers2 = [
            "Cliente/Proveedor", "Número Pago", "Fecha", "Monto", "Moneda",
            "Facturas Aplicables", "Facturas a Aplicar", "Pendiente en Facturas",
            "Diario", "Método de Pago",
        ]
        widths2 = [35, 20, 14, 18, 12, 18, 60, 25, 25, 25]
        for col, (header, width) in enumerate(zip(headers2, widths2)):
            ws2.write(0, col, header, header_fmt)
            ws2.set_column(col, col, width)

        for row_idx, line in enumerate(self.payment_line_ids, start=1):
            ws2.write(row_idx, 0, line.partner_name or "", text_fmt)
            ws2.write(row_idx, 1, line.payment_name or "", text_fmt)
            ws2.write(row_idx, 2, line.date or "", date_fmt)
            ws2.write(row_idx, 3, line.amount, money_fmt)
            ws2.write(row_idx, 4, line.currency_name or "", text_fmt)
            ws2.write(row_idx, 5, line.applicable_invoice_count, text_fmt)
            ws2.write(row_idx, 6, line.applicable_invoice_names or "", text_fmt)
            ws2.write(row_idx, 7, line.applicable_invoice_residual_summary or "", text_fmt)
            ws2.write(row_idx, 8, line.journal_name or "", text_fmt)
            ws2.write(row_idx, 9, line.payment_method_name or "", text_fmt)

        workbook.close()
        output.seek(0)
        return output.read()
