# -*- coding: utf-8 -*-

from odoo import _, models


class SngWarehouseAvailabilityXlsx(models.AbstractModel):
    _name = "report.sng_warehouse_availability_report.availability_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX de Disponibilidad por Almacenes"

    def generate_xlsx_report(self, workbook, data, wizards):
        title_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        text_format = workbook.add_format({"border": 1})
        quantity_format = workbook.add_format(
            {
                "border": 1,
                "align": "right",
                "num_format": '#,##0.00;[Red]-#,##0.00;"-"',
            }
        )

        for wizard in wizards:
            warehouses = wizard._get_warehouses()
            rows = wizard._get_report_rows()
            sheet = workbook.add_worksheet(_("Disponibilidad")[:31])
            last_warehouse_col = 1 + len(warehouses)
            supplier_col = last_warehouse_col + 1

            sheet.merge_range(
                0,
                0,
                1,
                0,
                _("Codigo"),
                header_format,
            )
            sheet.merge_range(
                0,
                1,
                1,
                1,
                _("Descripcion"),
                header_format,
            )
            quantity_title = _("Cantidad disponible - %s") % (
                wizard.warehouse_group_id.display_name
            )
            if len(warehouses) == 1:
                sheet.write(0, 2, quantity_title, title_format)
            else:
                sheet.merge_range(
                    0,
                    2,
                    0,
                    last_warehouse_col,
                    quantity_title,
                    title_format,
                )
            sheet.merge_range(
                0,
                supplier_col,
                1,
                supplier_col,
                _("Proveedor"),
                header_format,
            )

            for column, warehouse in enumerate(warehouses, start=2):
                sheet.write(1, column, warehouse.name, header_format)

            for row_number, row in enumerate(rows, start=2):
                sheet.write(row_number, 0, row["product_code"], text_format)
                sheet.write(row_number, 1, row["product_name"], text_format)
                for column, warehouse in enumerate(warehouses, start=2):
                    sheet.write_number(
                        row_number,
                        column,
                        row["quantity_by_warehouse"].get(warehouse.id, 0.0),
                        quantity_format,
                    )
                sheet.write(row_number, supplier_col, row["supplier_name"], text_format)

            sheet.freeze_panes(2, 2)
            sheet.autofilter(1, 0, max(len(rows) + 1, 2), supplier_col)
            sheet.set_row(0, 30)
            sheet.set_row(1, 25)
            sheet.set_column(0, 0, 18)
            sheet.set_column(1, 1, 38)
            sheet.set_column(2, last_warehouse_col, 18)
            sheet.set_column(supplier_col, supplier_col, 30)
