# -*- coding: utf-8 -*-

import base64
import calendar
import io
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .commission_target import MONTH_SELECTION

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class CommissionSettlement(models.Model):
    _name = "sng.commission.settlement"
    _description = "Liquidación mensual de comisión"
    _order = "year desc, month desc, salesperson_id"

    _sql_constraints = [
        (
            "sng_commission_settlement_unique_period",
            "unique(plan_id, salesperson_id, year, month)",
            "Ya existe una liquidación para este vendedor, plan y periodo.",
        ),
    ]

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    plan_id = fields.Many2one("sng.commission.plan", string="Plan", required=True, ondelete="restrict")
    company_id = fields.Many2one(related="plan_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="plan_id.currency_id", store=True, readonly=True)
    salesperson_id = fields.Many2one(
        "res.partner",
        string="Vendedor",
        required=True,
        domain="[('is_salesperson', '=', True)]",
    )
    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.today().year)
    month = fields.Selection(MONTH_SELECTION, string="Mes", required=True, default=lambda self: str(fields.Date.today().month))
    date_from = fields.Date(string="Inicio periodo", compute="_compute_period_dates", store=True)
    date_to = fields.Date(string="Fin periodo", compute="_compute_period_dates", store=True)
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("approved", "Aprobado"),
            ("closed", "Cerrado"),
        ],
        string="Estado",
        default="draft",
        required=True,
    )
    needs_recompute = fields.Boolean(string="Requiere recálculo", default=False, readonly=True)
    target_amount = fields.Monetary(string="Meta", currency_field="currency_id", readonly=True)
    actual_sales_amount = fields.Monetary(string="Venta real sin IVA", currency_field="currency_id", readonly=True)
    achievement_percentage = fields.Float(string="% cumplimiento", readonly=True)
    performance_rule_id = fields.Many2one("sng.commission.performance.rule", string="Regla cumplimiento", readonly=True)
    performance_factor = fields.Float(string="Factor aplicado", readonly=True)
    total_amount_applied_company = fields.Monetary(
        string="Total aplicado moneda compañía",
        compute="_compute_payment_totals",
        store=True,
        currency_field="currency_id",
    )
    gross_commission_amount = fields.Monetary(string="Comisión bruta", currency_field="currency_id", readonly=True)
    adjusted_commission_amount = fields.Monetary(string="Comisión a pagar", currency_field="currency_id", readonly=True)
    line_ids = fields.One2many("sng.commission.settlement.line", "settlement_id", string="Detalle", copy=False)
    line_count = fields.Integer(string="Líneas", compute="_compute_line_count")

    @api.depends("salesperson_id", "year", "month")
    def _compute_name(self):
        month_names = dict(MONTH_SELECTION)
        for record in self:
            salesperson = record.salesperson_id.display_name or _("Sin vendedor")
            month_name = month_names.get(record.month, "")
            record.name = f"{salesperson} - {month_name} {record.year}"

    @api.depends("year", "month")
    def _compute_period_dates(self):
        for record in self:
            if record.year and record.month:
                month = int(record.month)
                record.date_from = date(record.year, month, 1)
                record.date_to = date(record.year, month, calendar.monthrange(record.year, month)[1])
            else:
                record.date_from = False
                record.date_to = False

    @api.depends("line_ids")
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends("line_ids.amount_applied_company")
    def _compute_payment_totals(self):
        for record in self:
            record.total_amount_applied_company = sum(record.line_ids.mapped("amount_applied_company"))

    @api.constrains("date_from", "date_to", "plan_id")
    def _check_plan_coverage(self):
        for record in self:
            if not record.date_from or not record.date_to or not record.plan_id:
                continue
            if record.date_from < record.plan_id.date_start:
                raise ValidationError(_("El periodo de liquidación debe quedar dentro de la vigencia del plan."))
            if record.plan_id.date_end and record.date_to > record.plan_id.date_end:
                raise ValidationError(_("El periodo de liquidación debe quedar dentro de la vigencia del plan."))

    def _get_target_amount(self):
        self.ensure_one()
        target = self.env["sng.commission.target"].search(
            [
                ("plan_id", "=", self.plan_id.id),
                ("salesperson_id", "=", self.salesperson_id.id),
                ("year", "=", self.year),
                ("month", "=", self.month),
            ],
            limit=1,
        )
        return target.target_amount if target else 0.0

    def _get_actual_sales_amount(self):
        self.ensure_one()
        moves = self.env["account.move"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
                ("invoice_date", ">=", self.date_from),
                ("invoice_date", "<=", self.date_to),
            ]
        )
        rule_map = self._get_invoice_report_salesperson_rule_map(moves)
        matching_moves = moves.filtered(
            lambda move: self._get_invoice_report_salesperson(move, rule_map) == self.salesperson_id
        )
        return sum(self._get_invoice_report_untaxed_amount(move) for move in matching_moves)

    def _get_invoice_report_salesperson_rule_map(self, moves):
        """Mirror sng_invoice_report salesperson reassignment rules."""
        user_ids = moves.mapped("invoice_user_id").ids
        company_ids = moves.mapped("company_id").ids
        if not user_ids or not company_ids:
            return {}
        rules = self.env["invoice.report.salesperson.rule"].search(
            [
                ("active", "=", True),
                ("company_id", "in", company_ids),
                ("user_id", "in", user_ids),
            ]
        )
        return {
            (rule.company_id.id, rule.user_id.id): rule.salesperson_id
            for rule in rules
        }

    def _get_invoice_report_salesperson(self, move, rule_map=None):
        """Return the same salesperson used by sng_invoice_report."""
        if rule_map is None:
            rule_map = self._get_invoice_report_salesperson_rule_map(move)
        configured_salesperson = rule_map.get((move.company_id.id, move.invoice_user_id.id))
        if configured_salesperson:
            return configured_salesperson
        return move.salesperson_id or move.assigned_salesperson_id

    def _get_invoice_report_untaxed_amount(self, move):
        sign = -1 if move.move_type == "out_refund" else 1
        return sign * abs(move.amount_untaxed_signed)

    def _get_invoice_and_counterpart_lines(self, partial):
        self.ensure_one()
        if partial.debit_move_id.move_id.move_type == "out_invoice":
            return partial.debit_move_id, partial.credit_move_id
        if partial.credit_move_id.move_id.move_type == "out_invoice":
            return partial.credit_move_id, partial.debit_move_id
        return self.env["account.move.line"], self.env["account.move.line"]

    def _prepare_partial_line_vals(self, partial, performance_factor):
        self.ensure_one()
        invoice_line, counterpart_line = self._get_invoice_and_counterpart_lines(partial)
        if not invoice_line:
            return False

        invoice = invoice_line.move_id
        counterpart_move = counterpart_line.move_id
        if invoice.state != "posted":
            return False
        if invoice.payment_state == "reversed":
            return False
        if counterpart_move == partial.exchange_move_id:
            return False
        if not counterpart_move.origin_payment_id and not counterpart_move.statement_line_id:
            return False

        salesperson = invoice.salesperson_id or invoice.partner_id.assigned_salesperson_id
        if salesperson != self.salesperson_id:
            return False

        application_date = partial.max_date or counterpart_line.date or invoice.invoice_date or self.date_to
        if application_date < self.date_from or application_date > self.date_to:
            return False

        source_currency = invoice_line.currency_id or self.currency_id
        source_amount = (
            partial.debit_amount_currency if invoice_line == partial.debit_move_id else partial.credit_amount_currency
        )
        if not source_amount and source_currency == self.currency_id:
            source_amount = partial.amount

        total_amount = abs(invoice.amount_total)
        untaxed_ratio = abs(invoice.amount_untaxed) / total_amount if total_amount else 0.0
        untaxed_source = source_amount * untaxed_ratio
        untaxed_company = untaxed_source
        if source_currency != self.currency_id:
            untaxed_company = source_currency._convert(
                untaxed_source,
                self.currency_id,
                self.company_id,
                application_date,
            )

        due_date = invoice.invoice_date_due or invoice.invoice_date or application_date
        days_overdue = (application_date - due_date).days if due_date else 0
        aging_rule = self.plan_id._get_aging_rule(days_overdue)
        if not aging_rule:
            if days_overdue <= 0:
                raise UserError(
                    _("El plan %(plan)s no tiene configurado el bucket de antigüedad 'No vencido'.",
                      plan=self.plan_id.display_name)
                )
            raise UserError(
                _("No existe un bucket de antigüedad configurado para %(days)s días en el plan %(plan)s.",
                  days=days_overdue, plan=self.plan_id.display_name)
            )

        base_percentage = aging_rule.commission_percentage
        base_amount = self.currency_id.round(untaxed_company * base_percentage / 100.0)
        final_amount = self.currency_id.round(base_amount * performance_factor / 100.0)

        return {
            "settlement_id": self.id,
            "partial_reconcile_id": partial.id,
            "salesperson_id": self.salesperson_id.id,
            "invoice_id": invoice.id,
            "payment_id": counterpart_move.origin_payment_id.id,
            "payment_move_id": counterpart_move.id,
            "customer_id": invoice.partner_id.id,
            "source_currency_id": source_currency.id,
            "applied_date": application_date,
            "invoice_date": invoice.invoice_date,
            "invoice_due_date": invoice.invoice_date_due,
            "amount_applied_source": source_amount,
            "amount_applied_untaxed_source": untaxed_source,
            "amount_applied_company": untaxed_company,
            "days_overdue": days_overdue,
            "aging_rule_id": aging_rule.id,
            "aging_bucket_label": aging_rule.name,
            "base_commission_percentage": base_percentage,
            "base_commission_amount": base_amount,
            "performance_factor": performance_factor,
            "final_commission_amount": final_amount,
        }

    def _get_period_partials(self):
        self.ensure_one()
        partials = self.env["account.partial.reconcile"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("max_date", ">=", self.date_from),
                ("max_date", "<=", self.date_to),
                "|",
                ("debit_move_id.move_id.move_type", "=", "out_invoice"),
                ("credit_move_id.move_id.move_type", "=", "out_invoice"),
            ]
        )
        return partials

    def action_generate_settlement(self):
        for settlement in self:
            if settlement.state != "draft":
                raise UserError(_("Solo se pueden recalcular liquidaciones en borrador."))

            target_amount = settlement._get_target_amount()
            actual_sales = settlement._get_actual_sales_amount()
            achievement = (actual_sales / target_amount) * 100.0 if target_amount else 0.0
            performance_rule = settlement.plan_id._get_performance_rule(achievement)
            if not performance_rule:
                raise UserError(
                    _("No existe una regla de cumplimiento para %(value).2f%% en el plan %(plan)s.",
                      value=achievement, plan=settlement.plan_id.display_name)
                )

            settlement.line_ids.unlink()

            line_values = []
            for partial in settlement._get_period_partials():
                values = settlement._prepare_partial_line_vals(partial, performance_rule.payout_factor)
                if values:
                    line_values.append(values)

            if line_values:
                self.env["sng.commission.settlement.line"].create(line_values)

            gross_amount = sum(settlement.line_ids.mapped("base_commission_amount"))
            adjusted_amount = sum(settlement.line_ids.mapped("final_commission_amount"))
            settlement.write(
                {
                    "target_amount": target_amount,
                    "actual_sales_amount": actual_sales,
                    "achievement_percentage": achievement,
                    "performance_rule_id": performance_rule.id,
                    "performance_factor": performance_rule.payout_factor,
                    "gross_commission_amount": gross_amount,
                    "adjusted_commission_amount": adjusted_amount,
                    "needs_recompute": False,
                }
            )
        return True

    def action_approve(self):
        self.write({"state": "approved"})

    def action_close(self):
        self.write({"state": "closed"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref("sng_sales_commission.action_report_sng_commission_settlement").report_action(self)

    def action_print_payment_report_pdf(self):
        self.ensure_one()
        return self.env.ref("sng_sales_commission.action_report_sng_commission_payment_detail").report_action(self)

    def action_export_payment_report_xlsx(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("La librería Python 'xlsxwriter' es requerida para exportar este reporte."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        self._write_payment_report_xlsx(workbook)
        workbook.close()
        output.seek(0)

        filename = "reporte_pagos_comision_%s.xlsx" % (self.name or self.id)
        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(output.getvalue()),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_view_lines(self):
        self.ensure_one()
        return {
            "name": _("Detalle de comisión"),
            "type": "ir.actions.act_window",
            "res_model": "sng.commission.settlement.line",
            "view_mode": "list,form",
            "domain": [("settlement_id", "=", self.id)],
            "context": {"default_settlement_id": self.id},
        }

    def _mark_needs_recompute(self):
        drafts = self.filtered(lambda settlement: settlement.state == "draft")
        if drafts:
            drafts.sudo().write({"needs_recompute": True})

    def _get_payment_report_data(self):
        self.ensure_one()
        summary_by_key = {}
        details = []
        for line in self.line_ids.sorted(lambda rec: (rec.applied_date or date.min, rec.payment_id.id or 0, rec.invoice_id.name or "", rec.id)):
            payment_record = line.payment_id or line.payment_move_id
            payment_model = payment_record._name if payment_record else False
            payment_id = payment_record.id if payment_record else False
            key = (payment_model, payment_id, line.source_currency_id.id)
            if key not in summary_by_key:
                summary_by_key[key] = {
                    "payment": payment_record,
                    "payment_label": self._get_payment_report_payment_label(line),
                    "source_currency": line.source_currency_id,
                    "invoice_ids": set(),
                    "date_from": line.applied_date,
                    "date_to": line.applied_date,
                    "amount_applied_source": 0.0,
                    "amount_applied_untaxed_source": 0.0,
                    "amount_applied_company": 0.0,
                    "base_commission_amount": 0.0,
                    "final_commission_amount": 0.0,
                }
            summary = summary_by_key[key]
            summary["invoice_ids"].add(line.invoice_id.id)
            if line.applied_date:
                summary["date_from"] = min(filter(None, [summary["date_from"], line.applied_date]))
                summary["date_to"] = max(filter(None, [summary["date_to"], line.applied_date]))
            summary["amount_applied_source"] += line.amount_applied_source
            summary["amount_applied_untaxed_source"] += line.amount_applied_untaxed_source
            summary["amount_applied_company"] += line.amount_applied_company
            summary["base_commission_amount"] += line.base_commission_amount
            summary["final_commission_amount"] += line.final_commission_amount
            details.append(self._get_payment_report_detail_values(line))

        summaries = []
        for summary in summary_by_key.values():
            summary["invoice_count"] = len(summary.pop("invoice_ids"))
            summaries.append(summary)
        summaries.sort(
            key=lambda item: (
                item["date_from"] or date.min,
                item["payment_label"] or "",
                item["source_currency"].name or "",
            )
        )
        return {
            "summaries": summaries,
            "details": details,
            "totals": self._get_payment_report_totals(summaries),
        }

    def _get_payment_report_payment_label(self, line):
        self.ensure_one()
        if line.payment_id:
            return line.payment_id.name or line.payment_id.display_name
        if line.payment_move_id:
            return line.payment_move_id.name or line.payment_move_id.display_name
        return _("Sin pago")

    def _get_payment_report_detail_values(self, line):
        return {
            "line": line,
            "applied_date": line.applied_date,
            "payment": line.payment_id,
            "payment_move": line.payment_move_id,
            "payment_label": self._get_payment_report_payment_label(line),
            "invoice": line.invoice_id,
            "customer": line.customer_id,
            "source_currency": line.source_currency_id,
            "amount_applied_source": line.amount_applied_source,
            "amount_applied_untaxed_source": line.amount_applied_untaxed_source,
            "amount_applied_company": line.amount_applied_company,
            "invoice_date": line.invoice_date,
            "invoice_due_date": line.invoice_due_date,
            "days_overdue": line.days_overdue,
            "aging_bucket_label": line.aging_bucket_label,
            "base_commission_percentage": line.base_commission_percentage,
            "base_commission_amount": line.base_commission_amount,
            "performance_factor": line.performance_factor,
            "final_commission_amount": line.final_commission_amount,
        }

    def _get_payment_report_totals(self, summaries):
        return {
            "payment_count": len(summaries),
            "invoice_count": sum(summary["invoice_count"] for summary in summaries),
            "amount_applied_company": sum(summary["amount_applied_company"] for summary in summaries),
            "base_commission_amount": sum(summary["base_commission_amount"] for summary in summaries),
            "final_commission_amount": sum(summary["final_commission_amount"] for summary in summaries),
        }

    def _write_payment_report_xlsx(self, workbook):
        self.ensure_one()
        data = self._get_payment_report_data()
        formats = self._get_payment_report_xlsx_formats(workbook)
        self._write_payment_report_xlsx_summary(workbook, data, formats)
        self._write_payment_report_xlsx_detail(workbook, data, formats)

    def _get_payment_report_xlsx_formats(self, workbook):
        return {
            "title": workbook.add_format({"bold": True, "font_size": 16, "align": "center"}),
            "subtitle": workbook.add_format({"bold": True, "font_size": 11}),
            "warning": workbook.add_format({"bold": True, "font_color": "#9C6500", "bg_color": "#FFEB9C"}),
            "header": workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#4472C4", "border": 1}),
            "cell": workbook.add_format({"border": 1}),
            "date": workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd"}),
            "number": workbook.add_format({"border": 1, "num_format": "#,##0.00"}),
            "integer": workbook.add_format({"border": 1, "num_format": "#,##0"}),
            "total": workbook.add_format({"bold": True, "border": 1, "bg_color": "#E2EFDA", "num_format": "#,##0.00"}),
            "total_label": workbook.add_format({"bold": True, "border": 1, "bg_color": "#E2EFDA"}),
        }

    def _write_payment_report_xlsx_summary(self, workbook, data, formats):
        sheet = workbook.add_worksheet(_("Resumen")[:31])
        sheet.set_column("A:A", 28)
        sheet.set_column("B:B", 12)
        sheet.set_column("C:C", 12)
        sheet.set_column("D:E", 14)
        sheet.set_column("F:J", 18)
        row = self._write_payment_report_xlsx_header(sheet, formats, _("Resumen de pagos"), 9)
        headers = [
            _("Pago / asiento"),
            _("Moneda"),
            _("Facturas"),
            _("Desde"),
            _("Hasta"),
            _("Monto aplicado origen"),
            _("Monto sin IVA origen"),
            _("Monto compañía"),
            _("Comisión base"),
            _("Comisión final"),
        ]
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats["header"])
        row += 1
        for summary in data["summaries"]:
            sheet.write(row, 0, summary["payment_label"], formats["cell"])
            sheet.write(row, 1, summary["source_currency"].name, formats["cell"])
            sheet.write(row, 2, summary["invoice_count"], formats["integer"])
            sheet.write(row, 3, summary["date_from"], formats["date"])
            sheet.write(row, 4, summary["date_to"], formats["date"])
            sheet.write(row, 5, summary["amount_applied_source"], formats["number"])
            sheet.write(row, 6, summary["amount_applied_untaxed_source"], formats["number"])
            sheet.write(row, 7, summary["amount_applied_company"], formats["number"])
            sheet.write(row, 8, summary["base_commission_amount"], formats["number"])
            sheet.write(row, 9, summary["final_commission_amount"], formats["number"])
            row += 1
        totals = data["totals"]
        sheet.write(row, 0, _("Total"), formats["total_label"])
        sheet.write(row, 1, "", formats["total_label"])
        sheet.write(row, 2, totals["invoice_count"], formats["total"])
        sheet.write(row, 3, "", formats["total_label"])
        sheet.write(row, 4, "", formats["total_label"])
        sheet.write(row, 5, "", formats["total_label"])
        sheet.write(row, 6, "", formats["total_label"])
        sheet.write(row, 7, totals["amount_applied_company"], formats["total"])
        sheet.write(row, 8, totals["base_commission_amount"], formats["total"])
        sheet.write(row, 9, totals["final_commission_amount"], formats["total"])

    def _write_payment_report_xlsx_detail(self, workbook, data, formats):
        sheet = workbook.add_worksheet(_("Detalle")[:31])
        sheet.set_column("A:A", 14)
        sheet.set_column("B:D", 24)
        sheet.set_column("E:E", 36)
        sheet.set_column("F:F", 12)
        sheet.set_column("G:I", 18)
        sheet.set_column("J:K", 14)
        sheet.set_column("L:L", 12)
        sheet.set_column("M:M", 18)
        sheet.set_column("N:Q", 16)
        row = self._write_payment_report_xlsx_header(sheet, formats, _("Detalle de pagos"), 16)
        headers = [
            _("Fecha aplicación"),
            _("Pago"),
            _("Asiento de pago"),
            _("Factura"),
            _("Cliente"),
            _("Moneda"),
            _("Monto aplicado origen"),
            _("Monto sin IVA origen"),
            _("Monto compañía"),
            _("Fecha factura"),
            _("Fecha vencimiento"),
            _("Días vencidos"),
            _("Bucket"),
            _("% comisión base"),
            _("Comisión base"),
            _("Factor"),
            _("Comisión final"),
        ]
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats["header"])
        row += 1
        for detail in data["details"]:
            sheet.write(row, 0, detail["applied_date"], formats["date"])
            sheet.write(row, 1, detail["payment"].name if detail["payment"] else "", formats["cell"])
            sheet.write(row, 2, detail["payment_move"].name if detail["payment_move"] else "", formats["cell"])
            sheet.write(row, 3, detail["invoice"].name, formats["cell"])
            sheet.write(row, 4, detail["customer"].display_name, formats["cell"])
            sheet.write(row, 5, detail["source_currency"].name, formats["cell"])
            sheet.write(row, 6, detail["amount_applied_source"], formats["number"])
            sheet.write(row, 7, detail["amount_applied_untaxed_source"], formats["number"])
            sheet.write(row, 8, detail["amount_applied_company"], formats["number"])
            sheet.write(row, 9, detail["invoice_date"], formats["date"])
            sheet.write(row, 10, detail["invoice_due_date"], formats["date"])
            sheet.write(row, 11, detail["days_overdue"], formats["integer"])
            sheet.write(row, 12, detail["aging_bucket_label"], formats["cell"])
            sheet.write(row, 13, detail["base_commission_percentage"], formats["number"])
            sheet.write(row, 14, detail["base_commission_amount"], formats["number"])
            sheet.write(row, 15, detail["performance_factor"], formats["number"])
            sheet.write(row, 16, detail["final_commission_amount"], formats["number"])
            row += 1

    def _write_payment_report_xlsx_header(self, sheet, formats, title, last_col):
        sheet.merge_range(0, 0, 0, last_col, title, formats["title"])
        sheet.write(2, 0, _("Liquidación"), formats["subtitle"])
        sheet.write(2, 1, self.name or "")
        sheet.write(3, 0, _("Vendedor"), formats["subtitle"])
        sheet.write(3, 1, self.salesperson_id.display_name or "")
        sheet.write(4, 0, _("Plan"), formats["subtitle"])
        sheet.write(4, 1, self.plan_id.display_name or "")
        sheet.write(5, 0, _("Periodo"), formats["subtitle"])
        sheet.write(5, 1, "%s %s" % (dict(MONTH_SELECTION).get(self.month), self.year))
        if self.needs_recompute:
            sheet.merge_range(7, 0, 7, last_col, _("Advertencia: esta liquidación requiere recálculo."), formats["warning"])
            return 9
        return 7


class CommissionSettlementLine(models.Model):
    _name = "sng.commission.settlement.line"
    _description = "Detalle de liquidación de comisión"
    _order = "applied_date, id"

    _sql_constraints = [
        (
            "sng_commission_settlement_line_unique_partial",
            "unique(settlement_id, partial_reconcile_id)",
            "La misma conciliación parcial no puede repetirse dentro de una liquidación.",
        ),
    ]

    settlement_id = fields.Many2one("sng.commission.settlement", string="Liquidación", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="settlement_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="settlement_id.currency_id", store=True, readonly=True)
    partial_reconcile_id = fields.Many2one("account.partial.reconcile", string="Conciliación parcial", required=True, ondelete="cascade")
    salesperson_id = fields.Many2one("res.partner", string="Vendedor", required=True, domain="[('is_salesperson', '=', True)]")
    invoice_id = fields.Many2one("account.move", string="Factura", required=True, ondelete="restrict")
    payment_id = fields.Many2one("account.payment", string="Pago", ondelete="set null")
    payment_move_id = fields.Many2one("account.move", string="Asiento de pago", ondelete="set null")
    customer_id = fields.Many2one("res.partner", string="Cliente", required=True)
    source_currency_id = fields.Many2one("res.currency", string="Moneda origen", required=True)
    applied_date = fields.Date(string="Fecha aplicación", required=True)
    invoice_date = fields.Date(string="Fecha factura")
    invoice_due_date = fields.Date(string="Fecha vencimiento")
    amount_applied_source = fields.Monetary(string="Monto aplicado", currency_field="source_currency_id")
    amount_applied_untaxed_source = fields.Monetary(string="Monto aplicado sin IVA", currency_field="source_currency_id")
    amount_applied_company = fields.Monetary(string="Monto aplicado moneda compañía", currency_field="currency_id")
    days_overdue = fields.Integer(string="Días vencidos")
    aging_rule_id = fields.Many2one("sng.commission.aging.rule", string="Bucket", ondelete="restrict")
    aging_bucket_label = fields.Char(string="Bucket antigüedad")
    base_commission_percentage = fields.Float(string="% comisión base")
    base_commission_amount = fields.Monetary(string="Comisión base", currency_field="currency_id")
    performance_factor = fields.Float(string="Factor meta")
    final_commission_amount = fields.Monetary(string="Comisión final", currency_field="currency_id")
