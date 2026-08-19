# -*- coding: utf-8 -*-

from odoo import _, fields, models


class SngPurchaseSupplierReportXlsx(models.AbstractModel):
    _name = "report.sng_po_supplier_report.xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de órdenes de compra por proveedor"

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
            "datetime": workbook.add_format(
                {"border": 1, "num_format": "dd/mm/yyyy hh:mm"}
            ),
            "quantity": workbook.add_format(
                {
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "money": workbook.add_format(
                {
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "percent": workbook.add_format(
                {"border": 1, "num_format": '0.00"%"'}
            ),
            "subtotal_label": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#D9EAF7",
                    "border": 1,
                    "align": "right",
                }
            ),
            "subtotal": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#D9EAF7",
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
            "grand_label": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#D9EAD3",
                    "border": 1,
                    "align": "right",
                }
            ),
            "grand": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#D9EAD3",
                    "border": 1,
                    "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                }
            ),
        }

    def _write_metadata(self, sheet, wizard, formats, last_column, title):
        filters = wizard._get_filter_summary()
        sheet.merge_range(0, 0, 0, last_column, title, formats["title"])
        metadata = [
            (_("Compañía"), filters["company"]),
            (
                _("Período de confirmación"),
                "%s - %s"
                % (
                    fields.Date.to_string(filters["date_from"]),
                    fields.Date.to_string(filters["date_to"]),
                ),
            ),
            (_("Proveedores"), filters["suppliers"]),
            (_("Estado de recepción"), filters["reception_filter"]),
            (_("Moneda del resumen"), wizard.company_currency_id.name),
        ]
        for row, (label, value) in enumerate(metadata, start=1):
            sheet.write(row, 0, label, formats["meta_label"])
            sheet.write(row, 1, value or "")

    def _write_summary_sheet(self, workbook, wizard, formats):
        sheet = workbook.add_worksheet(_("Resumen")[:31])
        headers = [
            _("Proveedor"),
            _("Código"),
            _("Producto"),
            _("UdM base"),
            _("N.º órdenes"),
            _("Cantidad ordenada"),
            _("Cantidad recibida"),
            _("Cantidad pendiente"),
            _("Subtotal compañía"),
            _("Impuestos compañía"),
            _("Total compañía"),
            _("Subtotal pendiente"),
            _("Impuestos pendientes"),
            _("Total pendiente"),
        ]
        widths = [
            34, 16, 44, 14, 12, 17, 17, 17, 19, 19, 19, 19, 19, 19,
        ]
        self._write_metadata(
            sheet,
            wizard,
            formats,
            len(headers) - 1,
            _("RESUMEN DE ÓRDENES DE COMPRA POR PROVEEDOR"),
        )
        header_row = 7
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(header_row, column, header, formats["header"])
            sheet.set_column(column, column, width)

        row = header_row + 1
        for group in wizard._get_summary_groups():
            for values in group["rows"]:
                sheet.write(
                    row, 0, values["supplier"].display_name, formats["text"]
                )
                sheet.write(row, 1, values["product_code"], formats["text"])
                sheet.write(
                    row, 2, values["product"].display_name, formats["text"]
                )
                sheet.write(
                    row, 3, values["base_uom"].display_name, formats["text"]
                )
                sheet.write_number(
                    row, 4, values["order_count"], formats["quantity"]
                )
                for column, key in enumerate(
                    ("qty_ordered", "qty_received", "qty_pending"), start=5
                ):
                    sheet.write_number(
                        row, column, values[key], formats["quantity"]
                    )
                for column, key in enumerate(
                    (
                        "subtotal",
                        "tax",
                        "total",
                        "pending_subtotal",
                        "pending_tax",
                        "pending_total",
                    ),
                    start=8,
                ):
                    sheet.write_number(row, column, values[key], formats["money"])
                row += 1

            sheet.merge_range(
                row,
                0,
                row,
                7,
                _("SUBTOTAL %s") % group["supplier"].display_name,
                formats["subtotal_label"],
            )
            for column, key in enumerate(
                (
                    "subtotal",
                    "tax",
                    "total",
                    "pending_subtotal",
                    "pending_tax",
                    "pending_total",
                ),
                start=8,
            ):
                sheet.write_number(
                    row, column, group[key], formats["subtotal"]
                )
            row += 1

        totals = wizard._get_grand_totals()
        sheet.merge_range(
            row, 0, row, 7, _("TOTAL GENERAL"), formats["grand_label"]
        )
        for column, key in enumerate(
            (
                "subtotal",
                "tax",
                "total",
                "pending_subtotal",
                "pending_tax",
                "pending_total",
            ),
            start=8,
        ):
            sheet.write_number(row, column, totals[key], formats["grand"])

        sheet.freeze_panes(header_row + 1, 3)
        sheet.autofilter(
            header_row, 0, max(row - 1, header_row), len(headers) - 1
        )
        sheet.set_row(header_row, 32)

    def _write_detail_line(self, sheet, row, line, formats):
        text_values = {
            0: line.supplier_id.display_name,
            3: line.order_id.name,
            4: line.vendor_reference or "",
            5: line.product_code or "",
            6: line.product_id.display_name,
            10: line.uom_id.display_name,
            19: line.currency_id.name,
            23: line.base_uom_id.display_name,
            30: _("En tránsito")
            if line.reception_state == "transit"
            else _("Recibida"),
        }
        for column, value in text_values.items():
            sheet.write(row, column, value or "", formats["text"])
        sheet.write_datetime(
            row, 1, line.confirmation_date, formats["datetime"]
        )
        if line.planned_date:
            sheet.write_datetime(row, 2, line.planned_date, formats["datetime"])
        else:
            sheet.write(row, 2, "", formats["text"])
        for column, value in enumerate(
            (line.qty_ordered, line.qty_received, line.qty_pending), start=7
        ):
            sheet.write_number(row, column, value, formats["quantity"])
        sheet.write_number(row, 11, line.price_unit, formats["money"])
        sheet.write_number(row, 12, line.discount, formats["percent"])
        for column, value in enumerate(
            (
                line.subtotal,
                line.tax_amount,
                line.total,
                line.pending_subtotal,
                line.pending_tax,
                line.pending_total,
            ),
            start=13,
        ):
            sheet.write_number(row, column, value, formats["money"])
        for column, value in enumerate(
            (
                line.base_qty_ordered,
                line.base_qty_received,
                line.base_qty_pending,
            ),
            start=20,
        ):
            sheet.write_number(row, column, value, formats["quantity"])
        for column, value in enumerate(
            (
                line.subtotal_company,
                line.tax_company,
                line.total_company,
                line.pending_subtotal_company,
                line.pending_tax_company,
                line.pending_total_company,
            ),
            start=24,
        ):
            sheet.write_number(row, column, value, formats["money"])

    def _write_detail_sheet(self, workbook, wizard, formats):
        sheet = workbook.add_worksheet(_("Detalle")[:31])
        headers = [
            _("Proveedor"),
            _("Confirmación"),
            _("Llegada prevista"),
            _("Orden de compra"),
            _("Referencia proveedor"),
            _("Código"),
            _("Producto"),
            _("Ordenada"),
            _("Recibida"),
            _("Pendiente"),
            _("UdM compra"),
            _("Precio unitario"),
            _("Descuento %"),
            _("Subtotal OC"),
            _("Impuestos OC"),
            _("Total OC"),
            _("Subtotal pendiente OC"),
            _("Impuestos pendientes OC"),
            _("Total pendiente OC"),
            _("Moneda OC"),
            _("Ordenada base"),
            _("Recibida base"),
            _("Pendiente base"),
            _("UdM base"),
            _("Subtotal compañía"),
            _("Impuestos compañía"),
            _("Total compañía"),
            _("Subtotal pendiente compañía"),
            _("Impuestos pendientes compañía"),
            _("Total pendiente compañía"),
            _("Estado recepción"),
        ]
        widths = [
            32, 18, 18, 18, 22, 15, 42, 12, 12, 12, 13, 15, 13,
            16, 16, 16, 20, 20, 20, 11, 14, 14, 14, 13, 18, 18, 18,
            23, 23, 23, 17,
        ]
        self._write_metadata(
            sheet,
            wizard,
            formats,
            len(headers) - 1,
            _("DETALLE DE ÓRDENES DE COMPRA POR PROVEEDOR"),
        )
        header_row = 7
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(header_row, column, header, formats["header"])
            sheet.set_column(column, column, width)

        row = header_row + 1
        for supplier_group in wizard._get_detail_groups():
            for product_group in supplier_group["products"]:
                for line in product_group["lines"]:
                    self._write_detail_line(sheet, row, line, formats)
                    row += 1
                sheet.merge_range(
                    row,
                    0,
                    row,
                    23,
                    _("Subtotal producto: %s")
                    % product_group["product"].display_name,
                    formats["subtotal_label"],
                )
                sheet.write_number(
                    row, 26, product_group["total"], formats["subtotal"]
                )
                sheet.write_number(
                    row,
                    29,
                    product_group["pending_total"],
                    formats["subtotal"],
                )
                row += 1
            sheet.merge_range(
                row,
                0,
                row,
                23,
                _("SUBTOTAL PROVEEDOR: %s")
                % supplier_group["supplier"].display_name,
                formats["subtotal_label"],
            )
            sheet.write_number(
                row, 26, supplier_group["total"], formats["subtotal"]
            )
            sheet.write_number(
                row,
                29,
                supplier_group["pending_total"],
                formats["subtotal"],
            )
            row += 1

        totals = wizard._get_grand_totals()
        sheet.merge_range(
            row, 0, row, 23, _("TOTAL GENERAL"), formats["grand_label"]
        )
        sheet.write_number(row, 26, totals["total"], formats["grand"])
        sheet.write_number(
            row, 29, totals["pending_total"], formats["grand"]
        )
        sheet.freeze_panes(header_row + 1, 7)
        sheet.set_row(header_row, 44)

    def generate_xlsx_report(self, workbook, data, wizards):
        formats = self._get_formats(workbook)
        for wizard in wizards:
            if not wizard.line_ids:
                wizard._rebuild_lines()
            self._write_summary_sheet(workbook, wizard, formats)
            self._write_detail_sheet(workbook, wizard, formats)
