# -*- coding: utf-8 -*-
from odoo import models, fields


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
