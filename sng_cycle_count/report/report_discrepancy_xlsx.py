# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import AccessError


SUPERVISOR_GROUP = "sng_cycle_count.group_cycle_count_supervisor"


class CycleCountValuationPdf(models.AbstractModel):
    _name = "report.sng_cycle_count.report_cycle_count_valuation"
    _description = "Reporte PDF Valorizado de Conteo Cíclico"

    def _get_report_values(self, docids, data=None):
        if not self.env.user.has_group(SUPERVISOR_GROUP):
            raise AccessError(_("No tiene permiso para imprimir reportes valorizados."))
        return {
            "doc_ids": docids,
            "doc_model": "sng.cycle.count",
            "docs": self.env["sng.cycle.count"].browse(docids),
            "data": data or {},
        }


class CycleCountDiscrepancyXlsx(models.AbstractModel):
    _name = "report.sng_cycle_count.cycle_count_discrepancy_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte Excel de Discrepancias de Conteo Cíclico"

    def generate_xlsx_report(self, workbook, data, cycle_counts):
        for count in cycle_counts:
            # El nombre de hoja debe ser único y <=31 chars sin caracteres prohibidos
            sheet_name = (count.name or "Discrepancias").replace("/", "-")[:31]
            sheet = workbook.add_worksheet(sheet_name)

            title_fmt = workbook.add_format({"bold": True, "font_size": 14})
            head_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#D9E1F2"})
            text_fmt = workbook.add_format({"border": 1})
            num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.####"})

            # Encabezado
            sheet.write(0, 0, f"Discrepancias - {count.name}", title_fmt)
            sheet.write(1, 0, f"Fecha: {count.count_date}", text_fmt)
            sheet.write(2, 0, f"Operador: {count.user_id.name or '-'}", text_fmt)
            sheet.write(3, 0, f"Configuración: {count.config_id.name or '-'}", text_fmt)

            # Headers tabla
            headers = ["Producto", "Ubicación", "Lote/Serie", "Teórico", "Contado", "Diferencia", "Observaciones"]
            row = 5
            for col, h in enumerate(headers):
                sheet.write(row, col, h, head_fmt)

            discrepancy_lines = count.line_ids.filtered(lambda l: abs(l.difference_qty) > 0.0001)
            row += 1
            for line in discrepancy_lines:
                sheet.write(row, 0, line.product_id.display_name or "", text_fmt)
                sheet.write(row, 1, line.location_id.display_name or "", text_fmt)
                sheet.write(row, 2, line.lot_id.name or "", text_fmt)
                sheet.write_number(row, 3, line.theoretical_qty, num_fmt)
                sheet.write_number(row, 4, line.counted_qty, num_fmt)
                sheet.write_number(row, 5, line.difference_qty, num_fmt)
                sheet.write(row, 6, line.notes or "", text_fmt)
                row += 1

            if not discrepancy_lines:
                sheet.write(row, 0, "No se encontraron discrepancias.", text_fmt)

            # Anchos
            col_widths = [35, 25, 15, 12, 12, 12, 30]
            for i, w in enumerate(col_widths):
                sheet.set_column(i, i, w)


class CycleCountValuationXlsx(models.AbstractModel):
    _name = "report.sng_cycle_count.cycle_count_valuation_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte Excel Valorizado de Conteo Cíclico"

    def generate_xlsx_report(self, workbook, data, cycle_counts):
        if not self.env.user.has_group(SUPERVISOR_GROUP):
            raise AccessError(_("No tiene permiso para imprimir reportes valorizados."))

        for count in cycle_counts:
            sheet_name = ("Val_%s" % (count.name or "Conteo")).replace("/", "-")[:31]
            sheet = workbook.add_worksheet(sheet_name)

            title_fmt = workbook.add_format({"bold": True, "font_size": 14})
            head_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#D9E1F2"})
            text_fmt = workbook.add_format({"border": 1})
            qty_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.####"})
            cost_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.0000"})
            money_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})

            sheet.write(0, 0, f"Conteo valorizado - {count.name}", title_fmt)
            sheet.write(1, 0, f"Fecha: {count.count_date}", text_fmt)
            sheet.write(2, 0, f"Operador: {count.user_id.name or '-'}", text_fmt)
            sheet.write(3, 0, f"Configuración: {count.config_id.name or '-'}", text_fmt)

            summary = [
                ("Valor teórico", count.total_theoretical_value),
                ("Valor contado", count.total_counted_value),
                ("Sobrantes", count.total_gain_value),
                ("Faltantes", count.total_shortage_value),
                ("Diferencia neta", count.total_difference_value),
            ]
            for row, (label, value) in enumerate(summary, start=1):
                sheet.write(row, 5, label, head_fmt)
                sheet.write_number(row, 6, value, money_fmt)

            headers = [
                "Producto",
                "Ubicación",
                "Lote/Serie",
                "Teórico",
                "Contado",
                "Diferencia",
                "Costo unitario",
                "Valor teórico",
                "Valor contado",
                "Diferencia valorizada",
                "Observaciones",
            ]
            row = 7
            for col, header in enumerate(headers):
                sheet.write(row, col, header, head_fmt)

            report_lines = count.line_ids
            row += 1
            for line in report_lines:
                sheet.write(row, 0, line.product_id.display_name or "", text_fmt)
                sheet.write(row, 1, line.location_id.display_name or "", text_fmt)
                sheet.write(row, 2, line.lot_id.name or "", text_fmt)
                sheet.write_number(row, 3, line.theoretical_qty, qty_fmt)
                sheet.write_number(row, 4, line.counted_qty, qty_fmt)
                sheet.write_number(row, 5, line.difference_qty, qty_fmt)
                sheet.write_number(row, 6, line.unit_cost, cost_fmt)
                sheet.write_number(row, 7, line.theoretical_value, money_fmt)
                sheet.write_number(row, 8, line.counted_value, money_fmt)
                sheet.write_number(row, 9, line.difference_value, money_fmt)
                sheet.write(row, 10, line.notes or "", text_fmt)
                row += 1

            if not report_lines:
                sheet.write(row, 0, "El conteo no contiene líneas.", text_fmt)

            col_widths = [35, 25, 15, 12, 12, 12, 15, 16, 16, 20, 30]
            for col, width in enumerate(col_widths):
                sheet.set_column(col, col, width)
