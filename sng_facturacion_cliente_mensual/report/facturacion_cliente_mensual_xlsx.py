# -*- coding: utf-8 -*-

from odoo import _, models

from ..wizard.facturacion_cliente_mensual_wizard import VALUE_KEYS

MONEY_FORMAT = '#,##0.00;[Red]-#,##0.00;"-"'


class SngFacturacionClienteMensualXlsx(models.AbstractModel):
    _name = "report.sng_facturacion_cliente_mensual.facturacion_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Excel de facturación por cliente mensual detallado"

    def _get_formats(self, workbook):
        header = {
            "bold": True,
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        }
        return {
            "title": workbook.add_format(
                {"bold": True, "font_size": 14, "align": "center"}
            ),
            "subtitle": workbook.add_format(
                {"bold": True, "font_size": 12, "align": "center"}
            ),
            "filters": workbook.add_format(
                {"italic": True, "align": "center", "font_color": "#595959"}
            ),
            "month": workbook.add_format(
                dict(header, bg_color="#1F4E78", font_color="#FFFFFF")
            ),
            "period": workbook.add_format(
                dict(header, bg_color="#245501", font_color="#FFFFFF")
            ),
            "header": workbook.add_format(dict(header, bg_color="#D9E1F2")),
            "header_period": workbook.add_format(dict(header, bg_color="#D9EAD3")),
            "text": workbook.add_format({"border": 1}),
            "money": workbook.add_format({"border": 1, "num_format": MONEY_FORMAT}),
            "money_period": workbook.add_format(
                {"border": 1, "num_format": MONEY_FORMAT, "bg_color": "#F2F8EE"}
            ),
            "total_label": workbook.add_format(
                {"bold": True, "border": 1, "bg_color": "#D9EAD3", "align": "right"}
            ),
            "total": workbook.add_format(
                {
                    "bold": True,
                    "border": 1,
                    "bg_color": "#D9EAD3",
                    "num_format": MONEY_FORMAT,
                }
            ),
        }

    def _value_headers(self):
        return [
            _("Subtotal"),
            _("Descuento"),
            _("Notas de crédito"),
            _("VNAI"),
            _("Impuesto"),
            _("Total"),
        ]

    def _write_values(self, sheet, row, column, values, cell_format):
        for offset, key in enumerate(VALUE_KEYS):
            sheet.write_number(
                row, column + offset, round(values.get(key, 0.0), 2), cell_format
            )

    def generate_xlsx_report(self, workbook, data, wizards):
        formats = self._get_formats(workbook)
        for wizard in wizards:
            self._write_sheet(workbook, wizard, formats)

    def _write_sheet(self, workbook, wizard, formats):
        report = wizard._get_report_data()
        months = report["months"]
        width = len(VALUE_KEYS)
        sheet = workbook.add_worksheet(_("Facturación")[:31])

        blocks = [
            (month["label"], month["key"], formats["month"], formats["header"],
             formats["money"])
            for month in months
        ]
        blocks.append(
            (_("TOTAL PERÍODO"), None, formats["period"],
             formats["header_period"], formats["money_period"])
        )
        last_column = 1 + width * len(blocks)

        # Encabezado
        sheet.merge_range(
            0, 0, 0, last_column, wizard.company_id.name.upper(), formats["title"]
        )
        sheet.merge_range(
            1, 0, 1, last_column,
            _("FACTURACIÓN POR CLIENTE MENSUAL DETALLADO"),
            formats["subtitle"],
        )
        filters = wizard._get_filters_description()
        if filters:
            sheet.merge_range(2, 0, 2, last_column, filters, formats["filters"])

        month_row, header_row = 3, 4
        sheet.write(header_row, 0, _("Código cliente"), formats["header"])
        sheet.write(header_row, 1, _("Nombre comercial"), formats["header"])
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 45)
        sheet.set_column(2, last_column, 15)
        for index, (label, _key, month_fmt, header_fmt, _money) in enumerate(blocks):
            first = 2 + index * width
            sheet.merge_range(month_row, first, month_row, first + width - 1, label, month_fmt)
            for offset, header in enumerate(self._value_headers()):
                sheet.write(header_row, first + offset, header, header_fmt)
        sheet.set_row(header_row, 30)

        # Clientes
        row = header_row + 1
        for client in report["rows"]:
            sheet.write_string(row, 0, client["code"], formats["text"])
            sheet.write_string(row, 1, client["name"], formats["text"])
            for index, (_label, key, _m, _h, money_fmt) in enumerate(blocks):
                values = client["period"] if key is None else client["months"].get(key, {})
                self._write_values(sheet, row, 2 + index * width, values, money_fmt)
            row += 1

        # Total general
        totals = report["totals"]
        sheet.merge_range(row, 0, row, 1, _("TOTAL GENERAL :"), formats["total_label"])
        for index, (_label, key, _m, _h, _money) in enumerate(blocks):
            values = totals["period"] if key is None else totals["months"].get(key, {})
            self._write_values(sheet, row, 2 + index * width, values, formats["total"])

        sheet.freeze_panes(header_row + 1, 2)
        sheet.autofilter(header_row, 0, max(row - 1, header_row), last_column)
