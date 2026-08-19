# -*- coding: utf-8 -*-

from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SngProductCustomerReportWizard(models.TransientModel):
    _name = "sng.product.customer.report.wizard"
    _inherit = "sng.customer.product.report.wizard"
    _description = "Reporte de clientes por producto facturado"

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=False,
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_product_customer_report_wizard_product_rel",
        "wizard_id",
        "product_id",
        string="Productos",
        required=True,
        help="Seleccione uno o varios productos para consultar sus clientes.",
    )
    line_ids = fields.One2many(
        "sng.product.customer.report.line",
        "wizard_id",
        string="Resultados",
        readonly=True,
    )

    @api.constrains("product_ids")
    def _check_products(self):
        for wizard in self:
            if not wizard.product_ids:
                raise ValidationError(
                    _("Debe seleccionar al menos un producto.")
                )

    def _get_source_domain(self):
        self.ensure_one()
        return [
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("move_id.invoice_date", ">=", self.date_from),
            ("move_id.invoice_date", "<=", self.date_to),
            ("move_id.company_id", "=", self.company_id.id),
            ("display_type", "=", "product"),
            ("product_id", "in", self.product_ids.ids),
        ]

    def _prepare_report_line_values(self, source_line):
        self.ensure_one()
        return self._prepare_common_report_line_values(
            source_line,
            source_line.move_id.commercial_partner_id,
        )

    def _rebuild_lines(self):
        self.ensure_one()
        self._check_dates()
        self._check_products()
        self._check_company_access()
        self.line_ids.unlink()
        source_lines = self._get_source_lines()
        if not source_lines:
            raise UserError(
                _(
                    "No se encontraron clientes con productos facturados "
                    "para el período seleccionado."
                )
            )
        values_list = [
            self._prepare_report_line_values(source_line)
            for source_line in source_lines
        ]
        self.env["sng.product.customer.report.line"].create(values_list)
        return self.line_ids

    def _get_summary_rows(self):
        self.ensure_one()
        summary = OrderedDict()
        ordered_lines = self.line_ids.sorted(
            key=lambda line: (
                line.product_code or "",
                line.product_id.display_name or "",
                line.partner_id.display_name or "",
                line.product_id.id,
                line.partner_id.id,
            )
        )
        for line in ordered_lines:
            key = (line.product_id.id, line.partner_id.id)
            values = summary.setdefault(
                key,
                {
                    "product": line.product_id,
                    "product_code": line.product_code or "",
                    "product_name": line.product_id.display_name,
                    "partner": line.partner_id,
                    "partner_name": line.partner_id.display_name,
                    "uom": line.base_uom_id,
                    "quantity": 0.0,
                    "subtotal": 0.0,
                    "tax": 0.0,
                    "total": 0.0,
                },
            )
            values["quantity"] += line.base_quantity
            values["subtotal"] += line.subtotal_company
            values["tax"] += line.tax_amount_company
            values["total"] += line.total_company
        return list(summary.values())

    def _get_detail_groups(self):
        self.ensure_one()
        groups = OrderedDict()
        ordered_lines = self.line_ids.sorted(
            key=lambda line: (
                line.product_code or "",
                line.product_id.display_name or "",
                line.partner_id.display_name or "",
                line.invoice_date,
                line.move_id.id,
                line.source_line_id.id,
            )
        )
        for line in ordered_lines:
            key = (line.product_id.id, line.partner_id.id)
            group = groups.setdefault(
                key,
                {
                    "product": line.product_id,
                    "product_code": line.product_code or "",
                    "product_name": line.product_id.display_name,
                    "partner": line.partner_id,
                    "partner_name": line.partner_id.display_name,
                    "uom": line.base_uom_id,
                    "lines": [],
                    "quantity": 0.0,
                    "subtotal": 0.0,
                    "tax": 0.0,
                    "total": 0.0,
                },
            )
            group["lines"].append(line)
            group["quantity"] += line.base_quantity
            group["subtotal"] += line.subtotal_company
            group["tax"] += line.tax_amount_company
            group["total"] += line.total_company
        return list(groups.values())

    def action_view_report(self):
        self.ensure_one()
        self._rebuild_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Clientes por producto facturado"),
            "res_model": "sng.product.customer.report.line",
            "view_mode": "list,pivot",
            "views": [
                (
                    self.env.ref(
                        "sng_customer_product_invoice_report."
                        "view_product_customer_report_line_list"
                    ).id,
                    "list",
                ),
                (
                    self.env.ref(
                        "sng_customer_product_invoice_report."
                        "view_product_customer_report_line_pivot"
                    ).id,
                    "pivot",
                ),
            ],
            "search_view_id": self.env.ref(
                "sng_customer_product_invoice_report."
                "view_product_customer_report_line_search"
            ).id,
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "search_default_group_product": 1,
                "search_default_group_partner": 2,
                "product_customer_report_wizard_id": self.id,
                "pivot_measures": [
                    "base_quantity",
                    "subtotal_company",
                    "tax_amount_company",
                    "total_company",
                ],
            },
            "target": "current",
        }

    def action_open_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Clientes por producto facturado"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_print_pdf(self, rebuild=True):
        self.ensure_one()
        if rebuild or not self.line_ids:
            self._rebuild_lines()
        return self.env.ref(
            "sng_customer_product_invoice_report."
            "action_product_customer_report_pdf"
        ).report_action(self)

    def action_export_xlsx(self, rebuild=True):
        self.ensure_one()
        if rebuild or not self.line_ids:
            self._rebuild_lines()
        return self.env.ref(
            "sng_customer_product_invoice_report."
            "action_product_customer_report_xlsx"
        ).report_action(self)
