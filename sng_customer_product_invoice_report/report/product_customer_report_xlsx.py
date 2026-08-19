# -*- coding: utf-8 -*-

from odoo import _, fields, models


class SngProductCustomerReportXlsx(models.AbstractModel):
    _name = "report.sng_customer_product_invoice_report.sales_xlsx"
    _inherit = "report.sng_customer_product_invoice_report.product_xlsx"
    _description = "Reporte XLSX de clientes por producto facturado"

    def _write_metadata(self, sheet, wizard, formats, last_column):
        sheet.merge_range(
            0,
            0,
            0,
            last_column,
            _("CLIENTES POR PRODUCTO FACTURADO"),
            formats["title"],
        )
        product_names = ", ".join(
            wizard.product_ids.sorted("display_name").mapped("display_name")
        )
        metadata = [
            (_("Productos"), product_names),
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
        sheet = workbook.add_worksheet(_("Clientes por producto")[:31])
        headers = [
            _("Código"),
            _("Producto"),
            _("Cliente comercial"),
            _("UdM base"),
            _("Cantidad neta"),
            _("Subtotal CRC"),
            _("IVA CRC"),
            _("Total CRC"),
        ]
        widths = [16, 42, 35, 14, 16, 18, 18, 18]
        self._write_metadata(sheet, wizard, formats, len(headers) - 1)
        header_row = 5
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(header_row, column, header, formats["header"])
            sheet.set_column(column, column, width)

        row = header_row + 1
        for values in wizard._get_summary_rows():
            sheet.write(row, 0, values["product_code"], formats["text"])
            sheet.write(row, 1, values["product_name"], formats["text"])
            sheet.write(row, 2, values["partner_name"], formats["text"])
            sheet.write(row, 3, values["uom"].display_name, formats["text"])
            sheet.write_number(
                row, 4, values["quantity"], formats["quantity"]
            )
            sheet.write_number(row, 5, values["subtotal"], formats["money"])
            sheet.write_number(row, 6, values["tax"], formats["money"])
            sheet.write_number(row, 7, values["total"], formats["money"])
            row += 1

        totals = wizard._get_grand_totals()
        sheet.merge_range(
            row, 0, row, 4, _("TOTAL GENERAL"), formats["total_label"]
        )
        sheet.write_number(row, 5, totals["subtotal"], formats["total"])
        sheet.write_number(row, 6, totals["tax"], formats["total"])
        sheet.write_number(row, 7, totals["total"], formats["total"])
        sheet.freeze_panes(header_row + 1, 3)
        sheet.autofilter(
            header_row,
            0,
            max(row - 1, header_row),
            len(headers) - 1,
        )
        sheet.set_row(header_row, 30)
