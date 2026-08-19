# -*- coding: utf-8 -*-

from collections import OrderedDict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SngCustomerProductReportWizard(models.TransientModel):
    _name = "sng.customer.product.report.wizard"
    _description = "Reporte de productos facturados por cliente"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda de compañía",
        related="company_id.currency_id",
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=True,
        domain=[("customer_rank", ">", 0)],
        help=(
            "Se incluirán las facturas del cliente comercial y de todos "
            "sus contactos o sucursales."
        ),
    )
    date_from = fields.Date(
        string="Fecha desde",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Fecha hasta",
        required=True,
        default=fields.Date.context_today,
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_customer_product_report_wizard_product_rel",
        "wizard_id",
        "product_id",
        string="Productos",
        help="Dejar vacío para incluir todos los productos facturados.",
    )
    line_ids = fields.One2many(
        "sng.customer.product.report.line",
        "wizard_id",
        string="Resultados",
        readonly=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if (
                wizard.date_from
                and wizard.date_to
                and wizard.date_from > wizard.date_to
            ):
                raise ValidationError(
                    _("La fecha inicial no puede ser mayor que la fecha final.")
                )

    def _check_company_access(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise AccessError(
                _("No tiene acceso a la compañía seleccionada para el reporte.")
            )

    def _get_commercial_partner(self):
        self.ensure_one()
        return self.partner_id.commercial_partner_id

    def _get_source_domain(self):
        self.ensure_one()
        commercial_partner = self._get_commercial_partner()
        domain = [
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
            ("move_id.invoice_date", ">=", self.date_from),
            ("move_id.invoice_date", "<=", self.date_to),
            ("move_id.company_id", "=", self.company_id.id),
            ("move_id.commercial_partner_id", "=", commercial_partner.id),
            ("display_type", "=", "product"),
            ("product_id", "!=", False),
        ]
        if self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))
        return domain

    def _get_source_lines(self):
        self.ensure_one()
        self._check_company_access()
        return (
            self.env["account.move.line"]
            .with_company(self.company_id)
            .search(
                self._get_source_domain(),
                order="product_id, date, move_id, sequence, id",
            )
        )

    def _convert_to_company_currency(self, amount, currency, conversion_date):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if currency == company_currency:
            return company_currency.round(amount)
        return currency._convert(
            amount,
            company_currency,
            self.company_id,
            conversion_date,
            round=True,
        )

    def _prepare_report_line_values(self, source_line):
        self.ensure_one()
        return self._prepare_common_report_line_values(
            source_line,
            self._get_commercial_partner(),
        )

    def _prepare_common_report_line_values(self, source_line, commercial_partner):
        self.ensure_one()
        move = source_line.move_id
        product = source_line.product_id
        source_uom = source_line.product_uom_id or product.uom_id
        base_uom = product.uom_id
        currency = source_line.currency_id or move.currency_id
        conversion_date = move.invoice_date or move.date
        sign = -1.0 if move.move_type == "out_refund" else 1.0

        quantity = sign * abs(source_line.quantity)
        base_quantity = source_uom._compute_quantity(
            abs(source_line.quantity),
            base_uom,
        )
        base_quantity *= sign

        subtotal = sign * abs(source_line.price_subtotal)
        total = sign * abs(source_line.price_total)
        tax_amount = sign * abs(
            source_line.price_total - source_line.price_subtotal
        )

        return {
            "wizard_id": self.id,
            "company_id": self.company_id.id,
            "company_currency_id": self.company_id.currency_id.id,
            "partner_id": commercial_partner.id,
            "invoice_partner_id": move.partner_id.id,
            "move_id": move.id,
            "source_line_id": source_line.id,
            "invoice_date": move.invoice_date,
            "document_number": move.name or move.ref or str(move.id),
            "document_type": move.move_type,
            "is_credit_note": move.move_type == "out_refund",
            "product_id": product.id,
            "product_code": product.default_code or "",
            "uom_id": source_uom.id,
            "base_uom_id": base_uom.id,
            "currency_id": currency.id,
            "quantity": quantity,
            "base_quantity": base_quantity,
            "price_unit": abs(source_line.price_unit),
            "discount": abs(source_line.discount),
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total": total,
            "subtotal_company": self._convert_to_company_currency(
                subtotal, currency, conversion_date
            ),
            "tax_amount_company": self._convert_to_company_currency(
                tax_amount, currency, conversion_date
            ),
            "total_company": self._convert_to_company_currency(
                total, currency, conversion_date
            ),
        }

    def _rebuild_lines(self):
        self.ensure_one()
        self._check_dates()
        self._check_company_access()
        self.line_ids.unlink()
        source_lines = self._get_source_lines()
        if not source_lines:
            raise UserError(
                _(
                    "No se encontraron productos facturados para el cliente "
                    "y el período seleccionados."
                )
            )
        values_list = [
            self._prepare_report_line_values(source_line)
            for source_line in source_lines
        ]
        self.env["sng.customer.product.report.line"].create(values_list)
        return self.line_ids

    def _get_summary_rows(self):
        self.ensure_one()
        summary = OrderedDict()
        for line in self.line_ids.sorted(
            key=lambda item: (
                item.product_code or "",
                item.product_id.display_name or "",
                item.product_id.id,
            )
        ):
            values = summary.setdefault(
                line.product_id.id,
                {
                    "product": line.product_id,
                    "product_code": line.product_code or "",
                    "product_name": line.product_id.display_name,
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
                line.invoice_date,
                line.move_id.id,
                line.source_line_id.id,
            )
        )
        for line in ordered_lines:
            group = groups.setdefault(
                line.product_id.id,
                {
                    "product": line.product_id,
                    "product_code": line.product_code or "",
                    "product_name": line.product_id.display_name,
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

    def _get_grand_totals(self):
        self.ensure_one()
        return {
            "subtotal": sum(self.line_ids.mapped("subtotal_company")),
            "tax": sum(self.line_ids.mapped("tax_amount_company")),
            "total": sum(self.line_ids.mapped("total_company")),
        }

    def action_view_report(self):
        self.ensure_one()
        self._rebuild_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Productos facturados - %s")
            % self._get_commercial_partner().display_name,
            "res_model": "sng.customer.product.report.line",
            "view_mode": "list,pivot",
            "views": [
                (
                    self.env.ref(
                        "sng_customer_product_invoice_report."
                        "view_customer_product_report_line_list"
                    ).id,
                    "list",
                ),
                (
                    self.env.ref(
                        "sng_customer_product_invoice_report."
                        "view_customer_product_report_line_pivot"
                    ).id,
                    "pivot",
                ),
            ],
            "search_view_id": self.env.ref(
                "sng_customer_product_invoice_report."
                "view_customer_product_report_line_search"
            ).id,
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "search_default_group_product": 1,
                "customer_product_report_wizard_id": self.id,
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
            "name": _("Productos facturados por cliente"),
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
            "action_customer_product_report_pdf"
        ).report_action(self)

    def action_export_xlsx(self, rebuild=True):
        self.ensure_one()
        if rebuild or not self.line_ids:
            self._rebuild_lines()
        return self.env.ref(
            "sng_customer_product_invoice_report."
            "action_customer_product_report_xlsx"
        ).report_action(self)
