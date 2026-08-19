# -*- coding: utf-8 -*-

from odoo import _, fields, models


class SalesOrderInvoiceReportXlsx(models.AbstractModel):
    _name = "report.sng_sales_order_invoice_report.sales_ord_inv_xlsx"
    _description = "XLSX Reporte Ventas Ingresadas vs Facturadas"
    _inherit = "report.report_xlsx.abstract"

    def _get_snapshot_records(self, wizard):
        report_model = wizard.env["sng.sales.order.invoice.report"]
        domain = report_model._get_snapshot_domain(wizard.date_from, wizard.date_to)
        return report_model.search(
            domain,
            order="company_id, salesperson_id, order_create_date, sale_order_id, sale_order_line_id",
        )

    def _aggregate_summary(self, records):
        summary = {}
        for rec in records:
            key = (
                rec.company_id.id,
                rec.company_id.display_name,
                rec.salesperson_id.id,
                rec.salesperson_id.display_name or _("Sin vendedor"),
                rec.currency_id.name,
            )
            values = summary.setdefault(
                key,
                {
                    "ordered_qty": 0.0,
                    "ordered_untaxed": 0.0,
                    "ordered_total": 0.0,
                    "pending_qty": 0.0,
                    "pending_untaxed": 0.0,
                    "pending_total": 0.0,
                    "invoiced_qty": 0.0,
                    "invoiced_untaxed": 0.0,
                    "invoiced_total": 0.0,
                },
            )
            values["ordered_qty"] += rec.ordered_qty
            values["ordered_untaxed"] += rec.ordered_untaxed
            values["ordered_total"] += rec.ordered_total
            values["pending_qty"] += rec.pending_qty
            values["pending_untaxed"] += rec.pending_untaxed
            values["pending_total"] += rec.pending_total
            values["invoiced_qty"] += rec.invoiced_qty
            values["invoiced_untaxed"] += rec.invoiced_untaxed
            values["invoiced_total"] += rec.invoiced_total
        return summary

    def _write_filters(self, sheet, wizard, title_fmt, text_fmt):
        sheet.write(0, 0, "Reporte ventas ingresadas vs facturadas", title_fmt)
        sheet.write(1, 0, "Fecha desde", text_fmt)
        sheet.write(1, 1, fields.Date.to_string(wizard.date_from) if wizard.date_from else "")
        sheet.write(2, 0, "Fecha hasta", text_fmt)
        sheet.write(2, 1, fields.Date.to_string(wizard.date_to) if wizard.date_to else "")
        sheet.write(3, 0, "Companias", text_fmt)
        sheet.write(3, 1, ", ".join(wizard.company_ids.mapped("display_name")) or "-")
        sheet.write(4, 0, "Vendedores", text_fmt)
        sheet.write(4, 1, ", ".join(wizard.salesperson_ids.mapped("display_name")) or "-")
        sheet.write(5, 0, "Clientes", text_fmt)
        sheet.write(5, 1, ", ".join(wizard.partner_ids.mapped("display_name")) or "-")

    def generate_xlsx_report(self, workbook, data, wizards):
        header_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#D9EAF7"})
        text_fmt = workbook.add_format({"border": 1})
        title_fmt = workbook.add_format({"bold": True, "font_size": 13})
        qty_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.####"})
        amount_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})

        for wizard in wizards:
            records = self._get_snapshot_records(wizard)
            summary = self._aggregate_summary(records)

            summary_sheet = workbook.add_worksheet("Resumen por vendedor")
            detail_sheet = workbook.add_worksheet("Detalle por linea")

            self._write_filters(summary_sheet, wizard, title_fmt, text_fmt)

            summary_headers = [
                "Compania",
                "Vendedor",
                "Moneda",
                "Cant. ingresada",
                "Subtotal ingresado",
                "Total ingresado",
                "Cant. no facturada",
                "Subtotal no facturado",
                "Total no facturado",
                "Cant. facturada",
                "Subtotal facturado",
                "Total facturado",
            ]
            summary_row = 7
            for col, header in enumerate(summary_headers):
                summary_sheet.write(summary_row, col, header, header_fmt)

            for row_index, (key, values) in enumerate(sorted(summary.items(), key=lambda item: (item[0][0], item[0][3]))):
                row = summary_row + 1 + row_index
                summary_sheet.write(row, 0, key[1], text_fmt)
                summary_sheet.write(row, 1, key[3], text_fmt)
                summary_sheet.write(row, 2, key[4], text_fmt)
                summary_sheet.write_number(row, 3, values["ordered_qty"], qty_fmt)
                summary_sheet.write_number(row, 4, values["ordered_untaxed"], amount_fmt)
                summary_sheet.write_number(row, 5, values["ordered_total"], amount_fmt)
                summary_sheet.write_number(row, 6, values["pending_qty"], qty_fmt)
                summary_sheet.write_number(row, 7, values["pending_untaxed"], amount_fmt)
                summary_sheet.write_number(row, 8, values["pending_total"], amount_fmt)
                summary_sheet.write_number(row, 9, values["invoiced_qty"], qty_fmt)
                summary_sheet.write_number(row, 10, values["invoiced_untaxed"], amount_fmt)
                summary_sheet.write_number(row, 11, values["invoiced_total"], amount_fmt)

            summary_sheet.set_column(0, 2, 24)
            summary_sheet.set_column(3, 11, 16)
            summary_sheet.freeze_panes(summary_row + 1, 0)

            detail_headers = [
                "Ingreso sistema",
                "Fecha orden",
                "Orden",
                "Cliente",
                "Vendedor",
                "Compania",
                "Moneda",
                "Producto",
                "Categoria",
                "Estado orden",
                "Estado fact. orden",
                "Estado fact. linea",
                "Cant. ingresada",
                "Subtotal ingresado",
                "Total ingresado",
                "Cant. no facturada",
                "Subtotal no facturado",
                "Total no facturado",
                "Cant. facturada",
                "Subtotal facturado",
                "Total facturado",
            ]
            for col, header in enumerate(detail_headers):
                detail_sheet.write(0, col, header, header_fmt)

            for row_index, rec in enumerate(records, start=1):
                detail_sheet.write(
                    row_index, 0, fields.Datetime.to_string(rec.order_create_date) if rec.order_create_date else "", text_fmt
                )
                detail_sheet.write(
                    row_index, 1, fields.Datetime.to_string(rec.order_date) if rec.order_date else "", text_fmt
                )
                detail_sheet.write(row_index, 2, rec.order_name or "", text_fmt)
                detail_sheet.write(row_index, 3, rec.partner_id.display_name or "", text_fmt)
                detail_sheet.write(row_index, 4, rec.salesperson_id.display_name or "", text_fmt)
                detail_sheet.write(row_index, 5, rec.company_id.display_name or "", text_fmt)
                detail_sheet.write(row_index, 6, rec.currency_id.name or "", text_fmt)
                detail_sheet.write(row_index, 7, rec.product_id.display_name or "", text_fmt)
                detail_sheet.write(row_index, 8, rec.categ_id.display_name or "", text_fmt)
                detail_sheet.write(row_index, 9, dict(rec._fields["order_state"].selection).get(rec.order_state, ""), text_fmt)
                detail_sheet.write(row_index, 10, dict(rec._fields["order_invoice_status"].selection).get(rec.order_invoice_status, ""), text_fmt)
                detail_sheet.write(row_index, 11, dict(rec._fields["line_invoice_status"].selection).get(rec.line_invoice_status, ""), text_fmt)
                detail_sheet.write_number(row_index, 12, rec.ordered_qty, qty_fmt)
                detail_sheet.write_number(row_index, 13, rec.ordered_untaxed, amount_fmt)
                detail_sheet.write_number(row_index, 14, rec.ordered_total, amount_fmt)
                detail_sheet.write_number(row_index, 15, rec.pending_qty, qty_fmt)
                detail_sheet.write_number(row_index, 16, rec.pending_untaxed, amount_fmt)
                detail_sheet.write_number(row_index, 17, rec.pending_total, amount_fmt)
                detail_sheet.write_number(row_index, 18, rec.invoiced_qty, qty_fmt)
                detail_sheet.write_number(row_index, 19, rec.invoiced_untaxed, amount_fmt)
                detail_sheet.write_number(row_index, 20, rec.invoiced_total, amount_fmt)

            detail_sheet.set_column(0, 1, 20)
            detail_sheet.set_column(2, 8, 24)
            detail_sheet.set_column(9, 11, 18)
            detail_sheet.set_column(12, 20, 16)
            detail_sheet.freeze_panes(1, 0)
