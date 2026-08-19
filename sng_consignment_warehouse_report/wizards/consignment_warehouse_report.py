# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict
from datetime import datetime
from xml.sax.saxutils import escape

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class SngConsignmentWarehouseReportLine(models.TransientModel):
    _name = "sng.consignment.warehouse.report.line"
    _description = "Linea Reporte Bodegas Consignacion"
    _order = "currency_id, partner_id, root_location_id, product_description, id"

    wizard_id = fields.Many2one(
        "sng.consignment.warehouse.report.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one("res.company", related="wizard_id.company_id", store=True, readonly=True)
    date_report = fields.Date(related="wizard_id.date_report", store=True, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    root_location_id = fields.Many2one("stock.location", string="Bodega Consignacion", readonly=True)
    location_id = fields.Many2one("stock.location", string="Ubicacion", readonly=True)
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    product_code = fields.Char(string="Codigo de producto", readonly=True)
    product_description = fields.Char(string="Descripción", readonly=True)
    quantity = fields.Float(string="Cantidad", digits="Product Unit of Measure", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)
    unit_price = fields.Monetary(string="Valor unitario", currency_field="currency_id", readonly=True)
    total_amount = fields.Monetary(string="Total", currency_field="currency_id", readonly=True)
    is_zero_stock_line = fields.Boolean(string="Sin Stock", readonly=True)

    def _get_context_wizard(self):
        wizard_id = self.env.context.get("sng_consignment_warehouse_report_wizard_id")
        if not wizard_id and self:
            wizard_id = self[0].wizard_id.id
        wizard = self.env["sng.consignment.warehouse.report.wizard"].browse(wizard_id).exists()
        if not wizard:
            raise UserError("No se encontró el asistente asociado a este reporte.")
        return wizard

    def action_download_report(self):
        return self._get_context_wizard().action_download()

    def action_download_pdf_report(self):
        return self._get_context_wizard().action_download_pdf()

    def action_open_filters(self):
        return self._get_context_wizard().action_open_wizard()


class SngConsignmentWarehouseReportWizard(models.TransientModel):
    _name = "sng.consignment.warehouse.report.wizard"
    _description = "Wizard Reporte Bodegas Consignacion"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    date_report = fields.Date(
        string="Fecha del Reporte",
        required=True,
        default=fields.Date.context_today,
    )
    include_zero_stock = fields.Boolean(
        string="Incluir Clientes sin Stock",
        default=False,
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "sng_consignment_wh_wiz_partner_rel",
        "wizard_id",
        "partner_id",
        string="Clientes",
        domain="[('sale_location_id', '!=', False)]",
    )
    location_ids = fields.Many2many(
        "stock.location",
        "sng_consignment_wh_wiz_location_rel",
        "wizard_id",
        "location_id",
        string="Bodegas",
        domain="[('usage', '=', 'internal')]",
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_consignment_wh_wiz_product_rel",
        "wizard_id",
        "product_id",
        string="Productos",
        domain="[('is_storable', '=', True)]",
    )
    report_file = fields.Binary(string="Archivo", readonly=True)
    report_filename = fields.Char(string="Nombre de archivo", readonly=True)
    report_pdf_file = fields.Binary(string="Archivo PDF", readonly=True)
    report_pdf_filename = fields.Char(string="Nombre de archivo PDF", readonly=True)
    line_ids = fields.One2many(
        "sng.consignment.warehouse.report.line",
        "wizard_id",
        string="Resultados",
        readonly=True,
    )

    def action_generate_report(self):
        self.ensure_one()
        partners = self._get_report_partners()
        if not partners:
            raise UserError("No se encontraron clientes con bodega de consignación para los filtros seleccionados.")

        detail_rows, line_commands = self._build_report_snapshot(partners)
        if not line_commands:
            raise UserError(
                "Se encontraron %d clientes con los filtros aplicados, pero ninguno tiene productos en stock.\n"
                "Active \"Incluir Clientes sin Stock\" para verlos de todas formas." % len(partners)
            )

        excel_file = self._generate_excel(detail_rows)
        filename = "bodegas_consignacion_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self.write({
            "report_file": base64.b64encode(excel_file),
            "report_filename": filename,
            "report_pdf_file": False,
            "report_pdf_filename": False,
            "line_ids": [(5, 0, 0)] + line_commands,
        })
        return self.action_view_results()

    def action_view_results(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Bodegas Consignación",
            "res_model": "sng.consignment.warehouse.report.line",
            "view_mode": "list,pivot,form",
            "views": [
                (self.env.ref("sng_consignment_warehouse_report.view_sng_consignment_warehouse_report_line_list").id, "list"),
                (self.env.ref("sng_consignment_warehouse_report.view_sng_consignment_warehouse_report_line_pivot").id, "pivot"),
                (self.env.ref("sng_consignment_warehouse_report.view_sng_consignment_warehouse_report_line_form").id, "form"),
            ],
            "search_view_id": self.env.ref(
                "sng_consignment_warehouse_report.view_sng_consignment_warehouse_report_line_search"
            ).id,
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "search_default_group_currency": 1,
                "sng_consignment_warehouse_report_wizard_id": self.id,
                "pivot_measures": ["quantity", "total_amount"],
            },
            "target": "current",
        }

    def action_open_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
            "context": dict(self.env.context, sng_consignment_warehouse_report_wizard_id=self.id),
        }

    def action_download(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Primero genere el reporte antes de descargar el archivo.")
        excel_file = self._generate_excel(self._get_export_rows_from_lines())
        filename = self.report_filename or "bodegas_consignacion_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self.write({
            "report_file": base64.b64encode(excel_file),
            "report_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=report_file&filename=%s&download=true"
                   % (self._name, self.id, filename),
            "target": "self",
        }

    def action_download_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Primero genere el reporte antes de descargar el archivo.")
        pdf_file = self._generate_pdf(self._get_export_rows_from_lines())
        filename = self.report_pdf_filename or "bodegas_consignacion_%s.pdf" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self.write({
            "report_pdf_file": base64.b64encode(pdf_file),
            "report_pdf_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=report_pdf_file&filename=%s&download=true"
                   % (self._name, self.id, filename),
            "target": "self",
        }

    def _get_export_rows_from_lines(self):
        self.ensure_one()
        return [
            {
                "partner_name": line.partner_id.display_name or "",
                "partner_ref": getattr(line.partner_id, "unique_id", False) or "",
                "root_location_name": line.root_location_id.complete_name or "",
                "location_name": line.location_id.complete_name or "",
                "product_code": line.product_code or "",
                "product_description": line.product_description or "",
                "quantity": line.quantity or 0.0,
                "currency_name": line.currency_id.name or "",
                "unit_price": line.unit_price or 0.0,
                "total_amount": line.total_amount or 0.0,
            }
            for line in self.line_ids
        ]

    def _get_report_partners(self):
        domain = [
            ("sale_location_id", "!=", False),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.company_id.id),
        ]
        if self.partner_ids:
            domain.append(("id", "in", self.partner_ids.ids))
        if self.location_ids:
            domain.append(("sale_location_id", "in", self.location_ids.ids))
        return self.env["res.partner"].with_company(self.company_id).search(domain, order="name, id")

    def _build_report_snapshot(self, partners):
        detail_rows = []
        line_commands = []
        product_filter_ids = set(self.product_ids.ids)

        for partner in partners:
            root_location = partner.sale_location_id
            location_ids = self._get_internal_child_location_ids(root_location)
            qty_map = self._get_qty_map(location_ids, product_filter_ids)
            detail_count = 0

            for (product_id, location_id), quantity in sorted(qty_map.items(), key=lambda item: item[0]):
                product = self.env["product.product"].browse(product_id).with_company(self.company_id)
                location = self.env["stock.location"].browse(location_id)
                pricelist = partner.with_company(self.company_id).property_product_pricelist
                currency = pricelist.currency_id or self.company_id.currency_id
                unit_price = self._get_partner_product_price(partner, product, quantity, pricelist)
                total_amount = unit_price * quantity
                row = {
                    "partner_name": partner.display_name,
                    "partner_ref": getattr(partner, "unique_id", False) or "",
                    "root_location_name": root_location.complete_name,
                    "location_name": location.complete_name,
                    "product_code": product.default_code or "",
                    "product_description": product.name or "",
                    "quantity": quantity,
                    "currency_name": currency.name,
                    "pricelist_name": pricelist.display_name if pricelist else "",
                    "unit_price": unit_price,
                    "total_amount": total_amount,
                }
                detail_rows.append(row)
                line_commands.append((0, 0, {
                    "partner_id": partner.id,
                    "root_location_id": root_location.id,
                    "location_id": location.id,
                    "product_id": product.id,
                    "product_code": product.default_code or "",
                    "product_description": product.name or "",
                    "quantity": quantity,
                    "currency_id": currency.id,
                    "unit_price": unit_price,
                    "total_amount": total_amount,
                    "is_zero_stock_line": False,
                }))
                detail_count += 1

            if detail_count or not self.include_zero_stock:
                continue

            pricelist = partner.with_company(self.company_id).property_product_pricelist
            currency = pricelist.currency_id or self.company_id.currency_id
            detail_rows.append({
                "partner_name": partner.display_name,
                "partner_ref": getattr(partner, "unique_id", False) or "",
                "root_location_name": root_location.complete_name,
                "location_name": root_location.complete_name,
                "product_code": "",
                "product_description": "",
                "quantity": 0.0,
                "currency_name": currency.name,
                "pricelist_name": pricelist.display_name if pricelist else "",
                "unit_price": 0.0,
                "total_amount": 0.0,
            })
            line_commands.append((0, 0, {
                "partner_id": partner.id,
                "root_location_id": root_location.id,
                "location_id": root_location.id,
                "product_id": False,
                "product_code": "",
                "product_description": "",
                "quantity": 0.0,
                "currency_id": currency.id,
                "unit_price": 0.0,
                "total_amount": 0.0,
                "is_zero_stock_line": True,
            }))

        detail_rows.sort(key=lambda row: (
            row["currency_name"],
            row["partner_name"],
            row["root_location_name"],
            row["product_description"],
        ))
        return detail_rows, line_commands

    def _get_partner_product_price(self, partner, product, quantity, pricelist):
        if not pricelist:
            return 0.0
        try:
            return pricelist.with_company(self.company_id)._get_product_price(
                product,
                abs(quantity) or 1.0,
                currency=pricelist.currency_id,
                uom=product.uom_id,
                date=self.date_report,
            ) or 0.0
        except (TypeError, ZeroDivisionError, ValueError, UserError):
            return 0.0

    def _get_internal_child_location_ids(self, location):
        return self.env["stock.location"].search([
            ("id", "child_of", location.id),
            ("usage", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
        ]).ids

    def _get_qty_map(self, location_ids, product_filter_ids):
        qty_map = defaultdict(float)
        if not location_ids:
            return {}

        product_filter_sql = ""
        params = {
            "location_ids": tuple(location_ids),
        }
        if product_filter_ids:
            product_filter_sql = "AND product_id IN %(product_ids)s"
            params["product_ids"] = tuple(product_filter_ids)

        self.env.cr.execute("""
            SELECT product_id, location_id, COALESCE(SUM(quantity), 0)
            FROM stock_quant
            WHERE location_id IN %(location_ids)s
              {product_filter}
            GROUP BY product_id, location_id
        """.format(product_filter=product_filter_sql), params)
        for product_id, location_id, quantity in self.env.cr.fetchall():
            qty_map[(product_id, location_id)] += quantity or 0.0

        cleaned_qty_map = {}
        products = self.env["product.product"].browse(list({key[0] for key in qty_map}))
        rounding_by_product = {
            product.id: product.uom_id.rounding or 0.01
            for product in products
        }
        for key, quantity in qty_map.items():
            rounding = rounding_by_product.get(key[0], 0.01)
            if not float_is_zero(quantity, precision_rounding=rounding):
                cleaned_qty_map[key] = quantity
        return cleaned_qty_map

    def _generate_excel(self, detail_rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        bold_center_fmt = workbook.add_format({"bold": True, "align": "center"})
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#4472C4",
            "color": "white",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        text_fmt = workbook.add_format({"align": "left"})
        centered_text_fmt = workbook.add_format({"align": "center"})
        line_fmt = workbook.add_format({"num_format": "0", "align": "right"})
        qty_fmt = workbook.add_format({"num_format": "#,##0", "align": "right"})
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "align": "right"})

        sheet = workbook.add_worksheet("Reporte")

        headers = [
            "Linea",
            "Codigo de producto",
            "Descripción",
            "Cantidad",
            "Valor unitario",
            "Total",
        ]
        row = 0
        current_group = None
        line_number = 1
        group_quantity_total = 0.0
        group_amount_total = 0.0
        for index, item in enumerate(detail_rows):
            group = (
                item["partner_ref"],
                item["partner_name"],
                item["root_location_name"],
                item["location_name"],
                item["currency_name"],
            )
            if group != current_group:
                if current_group is not None:
                    row += 1
                sheet.merge_range(row, 0, row, 5, self.company_id.name, bold_center_fmt)
                row += 1
                sheet.merge_range(row, 0, row, 5, "Cliente: %s" % self._format_partner_label(item), centered_text_fmt)
                row += 1
                sheet.merge_range(row, 0, row, 5, "Fecha: %s" % self.date_report.strftime("%d/%m/%Y"), centered_text_fmt)
                row += 1
                sheet.merge_range(row, 0, row, 5, "Moneda: %s" % item["currency_name"], centered_text_fmt)
                row += 1
                sheet.merge_range(row, 0, row, 5, "Bodega: %s" % item["root_location_name"], centered_text_fmt)
                row += 1
                sheet.merge_range(row, 0, row, 5, "Ubicación: %s" % item["location_name"], centered_text_fmt)
                row += 1
                for col, header in enumerate(headers):
                    sheet.write(row, col, header, header_fmt)
                row += 1
                current_group = group
                group_quantity_total = 0.0
                group_amount_total = 0.0

            if item["product_description"]:
                sheet.write(row, 0, line_number, line_fmt)
            else:
                sheet.write(row, 0, "", text_fmt)
            sheet.write(row, 1, item["product_code"], text_fmt)
            sheet.write(row, 2, item["product_description"], text_fmt)
            sheet.write(row, 3, item["quantity"], qty_fmt)
            sheet.write(row, 4, item["unit_price"], money_fmt)
            sheet.write(row, 5, item["total_amount"], money_fmt)
            group_quantity_total += item["quantity"]
            group_amount_total += item["total_amount"]
            if item["product_description"]:
                line_number += 1
            row += 1

            next_item = detail_rows[index + 1] if index + 1 < len(detail_rows) else None
            next_group = (
                next_item["partner_ref"],
                next_item["partner_name"],
                next_item["root_location_name"],
                next_item["location_name"],
                next_item["currency_name"],
            ) if next_item else None
            if next_group != current_group:
                sheet.write(row, 2, "TOTAL", header_fmt)
                sheet.write(row, 3, group_quantity_total, qty_fmt)
                sheet.write(row, 5, group_amount_total, money_fmt)
                row += 1

        sheet.freeze_panes(6, 0)
        sheet.set_column("A:A", 10)
        sheet.set_column("B:B", 18)
        sheet.set_column("C:C", 42)
        sheet.set_column("D:D", 14)
        sheet.set_column("E:F", 16)

        workbook.close()
        output.seek(0)
        return output.read()

    def _generate_pdf(self, detail_rows):
        output = io.BytesIO()
        doc = SimpleDocTemplate(
            output,
            pagesize=landscape(letter),
            rightMargin=0.35 * inch,
            leftMargin=0.35 * inch,
            topMargin=0.35 * inch,
            bottomMargin=0.35 * inch,
        )
        styles = getSampleStyleSheet()
        normal_style = styles["Normal"]
        small_style = styles["BodyText"]
        description_style = styles["BodyText"].clone("ProductDescriptionLeft")
        normal_style.alignment = TA_CENTER
        small_style.fontSize = 7
        small_style.leading = 9
        small_style.alignment = TA_CENTER
        description_style.fontSize = 7
        description_style.leading = 9
        story = []

        current_group = None
        table_rows = []
        line_number = 1
        group_quantity_total = 0.0
        group_amount_total = 0.0
        for item in detail_rows:
            group = (
                item["partner_ref"],
                item["partner_name"],
                item["root_location_name"],
                item["location_name"],
                item["currency_name"],
            )
            if group != current_group:
                if table_rows:
                    table_rows.append([
                        "",
                        "",
                        "TOTAL",
                        self._format_quantity(group_quantity_total),
                        "",
                        self._format_number(group_amount_total),
                    ])
                    story.append(self._build_pdf_detail_table(table_rows))
                    story.append(Spacer(1, 0.15 * inch))
                    table_rows = []
                story.append(Paragraph("<b>%s</b>" % self._pdf_text(self.company_id.name), normal_style))
                story.append(Paragraph("Cliente: %s" % self._pdf_text(self._format_partner_label(item)), normal_style))
                story.append(Paragraph("Fecha: %s" % self.date_report.strftime("%d/%m/%Y"), normal_style))
                story.append(Paragraph("Moneda: %s" % self._pdf_text(item["currency_name"]), normal_style))
                table_rows = [[
                    "Linea",
                    "Codigo de producto",
                    "Descripción",
                    "Cantidad",
                    "Valor unitario",
                    "Total",
                ]]
                current_group = group
                group_quantity_total = 0.0
                group_amount_total = 0.0

            table_rows.append([
                str(line_number) if item["product_description"] else "",
                item["product_code"],
                Paragraph(self._pdf_text(item["product_description"]), description_style),
                self._format_quantity(item["quantity"]),
                self._format_number(item["unit_price"]),
                self._format_number(item["total_amount"]),
            ])
            if item["product_description"]:
                line_number += 1
            group_quantity_total += item["quantity"]
            group_amount_total += item["total_amount"]

        if table_rows:
            table_rows.append([
                "",
                "",
                "TOTAL",
                self._format_quantity(group_quantity_total),
                "",
                self._format_number(group_amount_total),
            ])
            story.append(self._build_pdf_detail_table(table_rows))
            story.append(Spacer(1, 0.2 * inch))

        doc.build(story)
        output.seek(0)
        return output.read()

    def _build_pdf_detail_table(self, rows):
        return Table(
            rows,
            repeatRows=1,
            colWidths=[0.45 * inch, 1.1 * inch, 3.2 * inch, 0.9 * inch, 1.1 * inch, 1.1 * inch],
            style=self._get_pdf_table_style(),
        )

    def _get_pdf_table_style(self):
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D9E2F3")),
        ])

    def _format_number(self, value):
        return "{:,.2f}".format(value or 0.0)

    def _format_quantity(self, value):
        return "{:,.0f}".format(value or 0.0)

    def _format_partner_label(self, item):
        partner_ref = item.get("partner_ref") or ""
        partner_name = item.get("partner_name") or ""
        return "%s - %s" % (partner_ref, partner_name) if partner_ref else partner_name

    def _pdf_text(self, value):
        return escape(value or "")
