# -*- coding: utf-8 -*-
from odoo import _, fields, models


class SngPurchaseSuggestionXlsx(models.AbstractModel):
    _name = "report.sng_purchase_suggestion_report.purchase_suggestion_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX Sugerido de Compras"

    def generate_xlsx_report(self, workbook, data, wizards):
        title_fmt = workbook.add_format({"bold": True, "font_size": 14})
        header_fmt = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#D9E2F3",
                "border": 1,
                "text_wrap": True,
                "valign": "vcenter",
            }
        )
        text_fmt = workbook.add_format({"border": 1})
        qty_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})

        for wizard in wizards:
            sheet = workbook.add_worksheet(_("Sugerido Compras"))
            filters = wizard._get_filter_summary()
            rows = [
                {
                    "product_name": line.product_name,
                    "product_code": line.product_code,
                    "supplier_name": line.supplier_name,
                    "qty_on_hand": line.qty_on_hand,
                    "qty_in_purchase": line.qty_in_purchase,
                    "qty_sold": line.qty_sold,
                    "is_outlier": line.is_outlier,
                    "avg_monthly_sales": line.avg_monthly_sales,
                    "suggested_purchase_qty": line.suggested_purchase_qty,
                    "qty_to_buy": line.qty_to_buy,
                }
                for line in wizard.line_ids
            ]
            row = 0

            sheet.write(row, 0, _("Reporte Sugerido de Compras"), title_fmt)
            row += 2

            filter_rows = [
                (_("Fecha desde"), fields.Date.to_string(filters["date_from"]) if filters["date_from"] else ""),
                (_("Fecha hasta"), fields.Date.to_string(filters["date_to"]) if filters["date_to"] else ""),
                (_("Dias analizados"), filters["analysis_days"]),
                (_("Dias de cobertura"), filters["coverage_days"]),
                (_("Companias"), filters["companies"]),
                (_("Grupo de almacenes"), filters["warehouse_group"]),
                (_("Almacenes"), filters["warehouses"]),
                (_("Bodegas"), filters["locations"]),
                (_("Productos"), filters["products"]),
                (_("Codigo producto"), filters["product_code"]),
            ]
            for label, value in filter_rows:
                sheet.write(row, 0, label)
                sheet.write(row, 1, value)
                row += 1

            row += 1
            sheet.freeze_panes(row + 1, 0)
            columns = [
                _("Producto"),
                _("Codigo articulo"),
                _("Proveedor sugerido"),
                _("Existencia actual"),
                _("En ordenes de compra"),
                _("Cantidad total vendida"),
                _("Venta atipica"),
                _("Promedio de venta mensual"),
                _("Sugerido de compra"),
                _("Sugerido menos existencias"),
            ]
            for col, name in enumerate(columns):
                sheet.write(row, col, name, header_fmt)

            row += 1
            for line in rows:
                sheet.write(row, 0, line["product_name"] or "", text_fmt)
                sheet.write(row, 1, line["product_code"] or "", text_fmt)
                sheet.write(row, 2, line["supplier_name"] or "", text_fmt)
                sheet.write_number(row, 3, line["qty_on_hand"] or 0.0, qty_fmt)
                sheet.write_number(row, 4, line["qty_in_purchase"] or 0.0, qty_fmt)
                sheet.write_number(row, 5, line["qty_sold"] or 0.0, qty_fmt)
                sheet.write(row, 6, _("Si") if line["is_outlier"] else _("No"), text_fmt)
                sheet.write_number(row, 7, line["avg_monthly_sales"] or 0.0, qty_fmt)
                sheet.write_number(row, 8, line["suggested_purchase_qty"] or 0.0, qty_fmt)
                sheet.write_number(row, 9, line["qty_to_buy"] or 0.0, qty_fmt)
                row += 1

            sheet.set_column(0, 0, 34)
            sheet.set_column(1, 2, 22)
            sheet.set_column(3, 9, 18)
