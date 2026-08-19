# -*- coding: utf-8 -*-

from collections import OrderedDict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class SngPurchaseSupplierReportWizard(models.TransientModel):
    _name = "sng.purchase.supplier.report.wizard"
    _description = "Reporte de órdenes de compra por proveedor"

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
    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    date_from = fields.Date(
        string="Fecha de confirmación desde",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Fecha de confirmación hasta",
        required=True,
        default=fields.Date.context_today,
    )
    supplier_ids = fields.Many2many(
        "res.partner",
        "sng_purchase_supplier_report_wizard_partner_rel",
        "wizard_id",
        "partner_id",
        string="Proveedores",
        domain=[("supplier_rank", ">", 0)],
        help="Dejar vacío para incluir todos los proveedores.",
    )
    reception_filter = fields.Selection(
        [
            ("all", "Todas"),
            ("transit", "En tránsito"),
        ],
        string="Estado de recepción",
        required=True,
        default="all",
        help=(
            "En tránsito incluye únicamente líneas con cantidad pendiente de "
            "recibir, incluso si la orden fue recibida parcialmente."
        ),
    )
    line_ids = fields.One2many(
        "sng.purchase.supplier.report.line",
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

    def _get_datetime_bounds(self):
        """Return inclusive-local-date bounds converted to naive UTC."""
        self.ensure_one()
        timezone = pytz.timezone(
            self.env.context.get("tz") or self.env.user.tz or "UTC"
        )
        start_local = timezone.localize(
            datetime.combine(self.date_from, time.min)
        )
        end_local = timezone.localize(
            datetime.combine(self.date_to + timedelta(days=1), time.min)
        )
        return (
            start_local.astimezone(pytz.UTC).replace(tzinfo=None),
            end_local.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    def _get_source_domain(self):
        self.ensure_one()
        start_utc, end_utc = self._get_datetime_bounds()
        domain = [
            ("order_id.state", "in", ("purchase", "done")),
            ("order_id.date_approve", ">=", start_utc),
            ("order_id.date_approve", "<", end_utc),
            ("company_id", "=", self.company_id.id),
            ("display_type", "=", False),
            ("product_id", "!=", False),
            ("is_downpayment", "=", False),
        ]
        if self.supplier_ids:
            domain.append(("order_id.partner_id", "in", self.supplier_ids.ids))
        return domain

    def _is_line_in_transit(self, source_line):
        rounding = source_line.product_uom.rounding
        return float_compare(
            source_line.product_qty,
            source_line.qty_received,
            precision_rounding=rounding,
        ) > 0

    def _get_source_lines(self):
        self.ensure_one()
        self._check_company_access()
        lines = (
            self.env["purchase.order.line"]
            .with_company(self.company_id)
            .search(
                self._get_source_domain(),
                order=(
                    "partner_id, product_id, date_approve, order_id, "
                    "sequence, id"
                ),
            )
        )
        if self.reception_filter == "transit":
            lines = lines.filtered(self._is_line_in_transit)
        return lines

    def _get_conversion_date(self, order):
        self.ensure_one()
        return fields.Datetime.context_timestamp(
            self, order.date_approve
        ).date()

    def _convert_to_company_currency(self, amount, currency, conversion_date):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if currency == company_currency:
            return amount
        return currency._convert(
            amount,
            company_currency,
            self.company_id,
            conversion_date,
            round=False,
        )

    def _get_pending_quantity(self, source_line):
        rounding = source_line.product_uom.rounding
        pending = max(source_line.product_qty - source_line.qty_received, 0.0)
        if float_is_zero(pending, precision_rounding=rounding):
            return 0.0
        return pending

    def _prepare_report_line_values(self, source_line):
        self.ensure_one()
        order = source_line.order_id
        product = source_line.product_id
        source_uom = source_line.product_uom
        base_uom = product.uom_id
        currency = order.currency_id
        pending_qty = self._get_pending_quantity(source_line)
        pending_ratio = (
            pending_qty / source_line.product_qty
            if source_line.product_qty > 0
            else 0.0
        )
        subtotal = source_line.price_subtotal
        tax_amount = source_line.price_tax
        total = source_line.price_total
        pending_subtotal = subtotal * pending_ratio
        pending_tax = tax_amount * pending_ratio
        pending_total = total * pending_ratio
        conversion_date = self._get_conversion_date(order)

        return {
            "wizard_id": self.id,
            "supplier_id": order.partner_id.id,
            "order_id": order.id,
            "source_line_id": source_line.id,
            "confirmation_date": order.date_approve,
            "planned_date": source_line.date_planned,
            "vendor_reference": order.partner_ref or "",
            "product_id": product.id,
            "product_code": product.default_code or "",
            "uom_id": source_uom.id,
            "base_uom_id": base_uom.id,
            "currency_id": currency.id,
            "qty_ordered": source_line.product_qty,
            "qty_received": source_line.qty_received,
            "qty_pending": pending_qty,
            "base_qty_ordered": source_uom._compute_quantity(
                source_line.product_qty, base_uom, round=False
            ),
            "base_qty_received": source_uom._compute_quantity(
                source_line.qty_received, base_uom, round=False
            ),
            "base_qty_pending": source_uom._compute_quantity(
                pending_qty, base_uom, round=False
            ),
            "price_unit": source_line.price_unit,
            "discount": source_line.discount,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total": total,
            "pending_subtotal": pending_subtotal,
            "pending_tax": pending_tax,
            "pending_total": pending_total,
            "subtotal_company": self._convert_to_company_currency(
                subtotal, currency, conversion_date
            ),
            "tax_company": self._convert_to_company_currency(
                tax_amount, currency, conversion_date
            ),
            "total_company": self._convert_to_company_currency(
                total, currency, conversion_date
            ),
            "pending_subtotal_company": self._convert_to_company_currency(
                pending_subtotal, currency, conversion_date
            ),
            "pending_tax_company": self._convert_to_company_currency(
                pending_tax, currency, conversion_date
            ),
            "pending_total_company": self._convert_to_company_currency(
                pending_total, currency, conversion_date
            ),
            "reception_state": "transit" if pending_qty > 0 else "received",
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
                    "No se encontraron líneas de órdenes de compra para los "
                    "filtros seleccionados."
                )
            )
        values_list = [
            self._prepare_report_line_values(source_line)
            for source_line in source_lines
        ]
        self.env["sng.purchase.supplier.report.line"].create(values_list)
        return self.line_ids

    def _get_summary_rows(self):
        self.ensure_one()
        summary = OrderedDict()
        ordered_lines = self.line_ids.sorted(
            key=lambda line: (
                line.supplier_id.display_name or "",
                line.product_code or "",
                line.product_id.display_name or "",
                line.product_id.id,
            )
        )
        for line in ordered_lines:
            key = (line.supplier_id.id, line.product_id.id)
            values = summary.setdefault(
                key,
                {
                    "supplier": line.supplier_id,
                    "product": line.product_id,
                    "product_code": line.product_code or "",
                    "base_uom": line.base_uom_id,
                    "order_ids": set(),
                    "qty_ordered": 0.0,
                    "qty_received": 0.0,
                    "qty_pending": 0.0,
                    "subtotal": 0.0,
                    "tax": 0.0,
                    "total": 0.0,
                    "pending_subtotal": 0.0,
                    "pending_tax": 0.0,
                    "pending_total": 0.0,
                },
            )
            values["order_ids"].add(line.order_id.id)
            values["qty_ordered"] += line.base_qty_ordered
            values["qty_received"] += line.base_qty_received
            values["qty_pending"] += line.base_qty_pending
            values["subtotal"] += line.subtotal_company
            values["tax"] += line.tax_company
            values["total"] += line.total_company
            values["pending_subtotal"] += line.pending_subtotal_company
            values["pending_tax"] += line.pending_tax_company
            values["pending_total"] += line.pending_total_company
        for values in summary.values():
            values["order_count"] = len(values["order_ids"])
        return list(summary.values())

    def _get_summary_groups(self):
        self.ensure_one()
        groups = OrderedDict()
        for row in self._get_summary_rows():
            supplier = row["supplier"]
            group = groups.setdefault(
                supplier.id,
                {
                    "supplier": supplier,
                    "rows": [],
                    "order_ids": set(),
                    "subtotal": 0.0,
                    "tax": 0.0,
                    "total": 0.0,
                    "pending_subtotal": 0.0,
                    "pending_tax": 0.0,
                    "pending_total": 0.0,
                },
            )
            group["rows"].append(row)
            group["order_ids"].update(row["order_ids"])
            for key in (
                "subtotal",
                "tax",
                "total",
                "pending_subtotal",
                "pending_tax",
                "pending_total",
            ):
                group[key] += row[key]
        for group in groups.values():
            group["order_count"] = len(group["order_ids"])
        return list(groups.values())

    def _get_detail_groups(self):
        self.ensure_one()
        supplier_groups = OrderedDict()
        lines = self.line_ids.sorted(
            key=lambda line: (
                line.supplier_id.display_name or "",
                line.product_code or "",
                line.product_id.display_name or "",
                line.confirmation_date,
                line.order_id.id,
                line.source_line_id.id,
            )
        )
        for line in lines:
            supplier_group = supplier_groups.setdefault(
                line.supplier_id.id,
                {
                    "supplier": line.supplier_id,
                    "products": OrderedDict(),
                    "total": 0.0,
                    "pending_total": 0.0,
                },
            )
            product_group = supplier_group["products"].setdefault(
                line.product_id.id,
                {
                    "product": line.product_id,
                    "product_code": line.product_code or "",
                    "base_uom": line.base_uom_id,
                    "lines": [],
                    "qty_ordered": 0.0,
                    "qty_received": 0.0,
                    "qty_pending": 0.0,
                    "total": 0.0,
                    "pending_total": 0.0,
                },
            )
            product_group["lines"].append(line)
            product_group["qty_ordered"] += line.base_qty_ordered
            product_group["qty_received"] += line.base_qty_received
            product_group["qty_pending"] += line.base_qty_pending
            product_group["total"] += line.total_company
            product_group["pending_total"] += line.pending_total_company
            supplier_group["total"] += line.total_company
            supplier_group["pending_total"] += line.pending_total_company

        result = []
        for group in supplier_groups.values():
            group["products"] = list(group["products"].values())
            result.append(group)
        return result

    def _get_grand_totals(self):
        self.ensure_one()
        return {
            "supplier_count": len(self.line_ids.mapped("supplier_id")),
            "product_count": len(self.line_ids.mapped("product_id")),
            "order_count": len(self.line_ids.mapped("order_id")),
            "subtotal": sum(self.line_ids.mapped("subtotal_company")),
            "tax": sum(self.line_ids.mapped("tax_company")),
            "total": sum(self.line_ids.mapped("total_company")),
            "pending_subtotal": sum(
                self.line_ids.mapped("pending_subtotal_company")
            ),
            "pending_tax": sum(self.line_ids.mapped("pending_tax_company")),
            "pending_total": sum(
                self.line_ids.mapped("pending_total_company")
            ),
        }

    def _get_filter_summary(self):
        self.ensure_one()
        return {
            "company": self.company_id.display_name,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "suppliers": (
                ", ".join(
                    self.supplier_ids.sorted("display_name").mapped(
                        "display_name"
                    )
                )
                or _("Todos")
            ),
            "reception_filter": (
                _("En tránsito")
                if self.reception_filter == "transit"
                else _("Todas")
            ),
        }

    def action_view_report(self):
        self.ensure_one()
        self._rebuild_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Órdenes de compra por proveedor"),
            "res_model": "sng.purchase.supplier.report.line",
            "view_mode": "list,pivot",
            "views": [
                (
                    self.env.ref(
                        "sng_purchase_order_supplier_report."
                        "view_purchase_supplier_report_line_list"
                    ).id,
                    "list",
                ),
                (
                    self.env.ref(
                        "sng_purchase_order_supplier_report."
                        "view_purchase_supplier_report_line_pivot"
                    ).id,
                    "pivot",
                ),
            ],
            "search_view_id": self.env.ref(
                "sng_purchase_order_supplier_report."
                "view_purchase_supplier_report_line_search"
            ).id,
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "search_default_group_supplier": 1,
                "search_default_group_product": 2,
                "purchase_supplier_report_wizard_id": self.id,
                "pivot_measures": [
                    "base_qty_ordered",
                    "base_qty_received",
                    "base_qty_pending",
                    "total_company",
                    "pending_total_company",
                ],
            },
            "target": "current",
        }

    def action_open_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Órdenes de compra por proveedor"),
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
            "sng_purchase_order_supplier_report."
            "action_purchase_supplier_report_pdf"
        ).report_action(self)

    def action_export_xlsx(self, rebuild=True):
        self.ensure_one()
        if rebuild or not self.line_ids:
            self._rebuild_lines()
        return self.env.ref(
            "sng_purchase_order_supplier_report."
            "action_purchase_supplier_report_xlsx"
        ).report_action(self)
