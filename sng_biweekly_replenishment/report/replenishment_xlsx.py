# -*- coding: utf-8 -*-

from odoo import _, models


class SngBiweeklyReplenishmentXlsx(models.AbstractModel):
    _name = "report.sng_biweekly_replenishment.replenishment_batch_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de Reabastecimiento Bisemanal"

    def generate_xlsx_report(self, workbook, data, batches):
        title_format = workbook.add_format(
            {"bold": True, "font_size": 14, "align": "center"}
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "bg_color": "#D9EAD3",
            }
        )
        text_format = workbook.add_format({"border": 1})
        qty_format = workbook.add_format(
            {
                "border": 1,
                "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
            }
        )
        shortage_format = workbook.add_format(
            {
                "border": 1,
                "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
                "bg_color": "#F4CCCC",
            }
        )

        for index, batch in enumerate(batches, start=1):
            sheet_name = (batch.name or _("Ciclo %s") % index).replace("/", "-")[:31]
            sheet = workbook.add_worksheet(sheet_name)
            sources = batch.config_id.source_line_ids.sorted(
                lambda source: (source.sequence, source.id)
            )
            fixed_headers = [
                _("Código"),
                _("Producto"),
                _("Unidad"),
                _("Salidas 14 días"),
                _("Demanda diaria"),
                _("Cobertura"),
                _("Seguridad"),
                _("Punto reorden"),
                _("Stock libre"),
                _("Stock previsto"),
                _("Entradas borrador"),
                _("Salidas borrador"),
                _("Stock proyectado"),
                _("Stock objetivo"),
                _("Sugerido"),
            ]
            trailing_headers = [_("Asignado"), _("Faltante"), _("Pickings")]
            headers = fixed_headers + [source.warehouse_id.code for source in sources] + trailing_headers

            sheet.merge_range(0, 0, 0, len(headers) - 1, _("Reabastecimiento %s") % batch.name, title_format)
            sheet.write(1, 0, _("Bodega Principal"), header_format)
            sheet.write(1, 1, batch.main_warehouse_id.display_name, text_format)
            sheet.write(1, 3, _("Período"), header_format)
            sheet.write(1, 4, "%s — %s" % (batch.period_start, batch.period_end), text_format)
            sheet.write(1, 6, _("Estado"), header_format)
            sheet.write(1, 7, dict(batch._fields["state"].selection).get(batch.state), text_format)

            header_row = 3
            for column, header in enumerate(headers):
                sheet.write(header_row, column, header, header_format)

            for row_number, line in enumerate(batch.line_ids, start=header_row + 1):
                values = [
                    line.product_code or "",
                    line.product_id.with_context(display_default_code=False).display_name,
                    line.uom_id.display_name,
                    line.demand_qty,
                    line.daily_demand,
                    line.coverage_days,
                    line.safety_days,
                    line.reorder_point,
                    line.free_qty,
                    line.forecast_qty,
                    line.draft_in_qty,
                    line.draft_out_qty,
                    line.projected_qty,
                    line.target_stock,
                    line.suggested_qty,
                ]
                for column, value in enumerate(values):
                    cell_format = text_format if column < 3 else qty_format
                    if column < 3:
                        sheet.write(row_number, column, value, cell_format)
                    else:
                        sheet.write_number(row_number, column, value or 0.0, cell_format)

                source_start = len(fixed_headers)
                for offset, source in enumerate(sources):
                    quantity = sum(
                        line.allocation_ids.filtered(
                            lambda allocation: allocation.source_id == source
                        ).mapped("allocated_qty")
                    )
                    sheet.write_number(row_number, source_start + offset, quantity, qty_format)

                trailing_start = source_start + len(sources)
                sheet.write_number(row_number, trailing_start, line.allocated_qty, qty_format)
                sheet.write_number(
                    row_number,
                    trailing_start + 1,
                    line.shortage_qty,
                    shortage_format if line.shortage_qty else qty_format,
                )
                references = ", ".join(line.allocation_ids.mapped("picking_id.name"))
                sheet.write(row_number, trailing_start + 2, references, text_format)

            last_row = max(header_row + len(batch.line_ids), header_row + 1)
            sheet.freeze_panes(header_row + 1, 3)
            sheet.autofilter(header_row, 0, last_row, len(headers) - 1)
            sheet.set_column(0, 0, 16)
            sheet.set_column(1, 1, 40)
            sheet.set_column(2, 2, 12)
            sheet.set_column(3, len(headers) - 2, 14)
            sheet.set_column(len(headers) - 1, len(headers) - 1, 24)

