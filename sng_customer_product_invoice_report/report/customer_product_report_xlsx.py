# -*- coding: utf-8 -*-

from odoo import _, fields, models


class SngCustomerProductReportXlsx(models.AbstractModel):
    _name = "report.sng_customer_product_invoice_report.product_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de productos facturados por cliente"

    def _get_formats(self, workbook):
        return {
            "title": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 15,
                    "align": "center",
                    "valign": "vcenter",
                }
            ),
            "meta_label": workbook.add_format({"bold": True}),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#1F4E78",
                    "font_color": "#FFFFFF",
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "text": workbook.add_format({"border": 1}),
            "text_credit": workbook.add_format(
                {"border": 1, "font_color": "#C00000"}
            ),
            "quantity": workbook.add_format(
                {
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "quantity_credit": workbook.add_format(
                {
                    "border": 1,
                    "font_color": "#C00000",
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "money": workbook.add_format(
                {
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "money_credit": workbook.add_format(
                {
                    "border": 1,
                    "font_color": "#C00000",
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "percent": workbook.add_format(
                {"border": 1, "num_format": '0.00"%"'}
            ),
            "total_label": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#D9EAD3",
                    "border": 1,
                    "align": "right",
                }
            ),
            "total": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#D9EAD3",
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
        }

    def _write_metadata(self, sheet, wizard, formats, last_column):
        sheet.merge_range(
            0,
            0,
            0,
            last_column,
            _("PRODUCTOS FACTURADOS POR CLIENTE"),
            formats["title"],
        )
        metadata = [
            (_("Cliente comercial"), wizard._get_commercial_partner().display_name),
            (_("Compañía"), wizard.company_id.display_name),
            (
                _("Período"),
                "%s - %s"
                % (
                    fields.Date.to_string(wizard.date_from),
                    fields.Date.to_string(wizard.date_to),
                ),
            ),
        ]
        for row, (label, value) in enumerate(metadata, start=1):
            sheet.write(row, 0, label, formats["meta_label"])
            sheet.write(row, 1, value or "")

    def _write_summary_sheet(self, workbook, wizard, formats):
        sheet = workbook.add_worksheet(_("Resumen por producto")[:31])
        headers = [
            _("Código"),
            _("Producto"),
            _("UdM base"),
            _("Cantidad neta"),
            _("Subtotal CRC"),
            _("IVA CRC"),
            _("Total CRC"),
        ]
        widths = [16, 45, 14, 16, 18, 18, 18]
        self._write_metadata(sheet, wizard, formats, len(headers) - 1)
        header_row = 5
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(header_row, column, header, formats["header"])
            sheet.set_column(column, column, width)

        row = header_row + 1
        for values in wizard._get_summary_rows():
            sheet.write(row, 0, values["product_code"], formats["text"])
            sheet.write(row, 1, values["product_name"], formats["text"])
            sheet.write(row, 2, values["uom"].display_name, formats["text"])
            sheet.write_number(
                row, 3, values["quantity"], formats["quantity"]
            )
            sheet.write_number(row, 4, values["subtotal"], formats["money"])
            sheet.write_number(row, 5, values["tax"], formats["money"])
            sheet.write_number(row, 6, values["total"], formats["money"])
            row += 1

        totals = wizard._get_grand_totals()
        sheet.merge_range(
            row, 0, row, 3, _("TOTAL GENERAL"), formats["total_label"]
        )
        sheet.write_number(row, 4, totals["subtotal"], formats["total"])
        sheet.write_number(row, 5, totals["tax"], formats["total"])
        sheet.write_number(row, 6, totals["total"], formats["total"])
        sheet.freeze_panes(header_row + 1, 2)
        sheet.autofilter(
            header_row,
            0,
            max(row - 1, header_row),
            len(headers) - 1,
        )
        sheet.set_row(header_row, 30)

    def _write_detail_sheet(self, workbook, wizard, formats):
        sheet = workbook.add_worksheet(_("Detalle")[:31])
        headers = [
            _("Fecha"),
            _("Tipo"),
            _("Documento"),
            _("Cliente comercial"),
            _("Contacto facturado"),
            _("Código"),
            _("Producto"),
            _("Cantidad"),
            _("UdM"),
            _("Precio unitario"),
            _("Descuento %"),
            _("Subtotal"),
            _("IVA"),
            _("Total"),
            _("Moneda"),
            _("Cantidad base"),
            _("UdM base"),
            _("Subtotal CRC"),
            _("IVA CRC"),
            _("Total CRC"),
        ]
        widths = [
            12, 17, 20, 28, 28, 15, 42, 13, 12, 16,
            13, 16, 16, 16, 10, 15, 12, 17, 17, 17,
        ]
        self._write_metadata(sheet, wizard, formats, len(headers) - 1)
        header_row = 5
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(header_row, column, header, formats["header"])
            sheet.set_column(column, column, width)

        document_labels = {
            "out_invoice": _("Factura"),
            "out_refund": _("Nota de crédito"),
        }
        row = header_row + 1
        for group in wizard._get_detail_groups():
            for line in group["lines"]:
                text_format = (
                    formats["text_credit"]
                    if line.is_credit_note
                    else formats["text"]
                )
                quantity_format = (
                    formats["quantity_credit"]
                    if line.is_credit_note
                    else formats["quantity"]
                )
                money_format = (
                    formats["money_credit"]
                    if line.is_credit_note
                    else formats["money"]
                )
                values = [
                    fields.Date.to_string(line.invoice_date),
                    document_labels.get(line.document_type, line.document_type),
                    line.document_number,
                    line.partner_id.display_name,
                    line.invoice_partner_id.display_name,
                    line.product_code or "",
                    line.product_id.display_name,
                ]
                for column, value in enumerate(values):
                    sheet.write(row, column, value or "", text_format)
                sheet.write_number(row, 7, line.quantity, quantity_format)
                sheet.write(row, 8, line.uom_id.display_name, text_format)
                sheet.write_number(row, 9, line.price_unit, money_format)
                sheet.write_number(row, 10, line.discount, formats["percent"])
                sheet.write_number(row, 11, line.subtotal, money_format)
                sheet.write_number(row, 12, line.tax_amount, money_format)
                sheet.write_number(row, 13, line.total, money_format)
                sheet.write(row, 14, line.currency_id.name, text_format)
                sheet.write_number(
                    row, 15, line.base_quantity, quantity_format
                )
                sheet.write(
                    row, 16, line.base_uom_id.display_name, text_format
                )
                sheet.write_number(
                    row, 17, line.subtotal_company, money_format
                )
                sheet.write_number(
                    row, 18, line.tax_amount_company, money_format
                )
                sheet.write_number(row, 19, line.total_company, money_format)
                row += 1

        last_data_row = row - 1
        totals = wizard._get_grand_totals()
        sheet.merge_range(
            row, 0, row, 16, _("TOTAL GENERAL CRC"), formats["total_label"]
        )
        sheet.write_number(row, 17, totals["subtotal"], formats["total"])
        sheet.write_number(row, 18, totals["tax"], formats["total"])
        sheet.write_number(row, 19, totals["total"], formats["total"])
        sheet.freeze_panes(header_row + 1, 3)
        sheet.autofilter(
            header_row,
            0,
            max(last_data_row, header_row),
            len(headers) - 1,
        )
        sheet.set_row(header_row, 32)

    def generate_xlsx_report(self, workbook, data, wizards):
        formats = self._get_formats(workbook)
        for wizard in wizards:
            if not wizard.line_ids:
                wizard._rebuild_lines()
            self._write_summary_sheet(workbook, wizard, formats)
            self._write_detail_sheet(workbook, wizard, formats)
