# -*- coding: utf-8 -*-
from odoo import _, fields, models

# Etiquetas de estado en el XLSX (mismas del Excel de compras original).
ESTADO_XLSX = {
    "datos_incompletos": "DATOS INCOMPLETOS",
    "quiebre": "QUIEBRE PROYECTADO",
    "reordenar": "REORDENAR",
    "exceso": "EXCESO",
    "inestable": "DEMANDA INESTABLE",
    "saludable": "SALUDABLE",
}


class SngAnalisisComprasXlsx(models.AbstractModel):
    _name = "report.sng_analisis_compras.analisis_compras_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Reporte XLSX Análisis de Compras"

    def generate_xlsx_report(self, workbook, data, wizards):
        fmt_title = workbook.add_format({"bold": True, "font_size": 13})
        fmt_filter_lbl = workbook.add_format({"bold": True, "font_size": 9})
        fmt_filter_val = workbook.add_format({"font_size": 9})
        fmt_header = workbook.add_format({
            "bold": True, "font_size": 9, "align": "center", "valign": "vcenter",
            "bg_color": "#1F4E79", "font_color": "#FFFFFF",
            "border": 1, "text_wrap": True,
        })
        fmt_text = workbook.add_format({"font_size": 8, "align": "left", "border": 1})
        fmt_num = workbook.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0"})
        fmt_dec = workbook.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0.0"})
        fmt_dec2 = workbook.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0.00"})
        fmt_money = workbook.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0.00"})
        fmt_red = workbook.add_format({
            "font_size": 8, "align": "right", "border": 1,
            "num_format": "#,##0.0", "bg_color": "#FFCCCC",
        })
        fmt_amber = workbook.add_format({
            "font_size": 8, "align": "right", "border": 1,
            "num_format": "#,##0.0", "bg_color": "#FFE5CC",
        })
        fmt_green = workbook.add_format({
            "font_size": 8, "align": "right", "border": 1,
            "num_format": "#,##0.0", "bg_color": "#CCFFCC",
        })
        fmt_total_lbl = workbook.add_format({
            "bold": True, "font_size": 8, "align": "left",
            "border": 1, "bg_color": "#D9D9D9",
        })
        fmt_total_num = workbook.add_format({
            "bold": True, "font_size": 8, "align": "right",
            "border": 1, "num_format": "#,##0", "bg_color": "#D9D9D9",
        })
        formats = {
            "text": fmt_text, "num": fmt_num, "dec": fmt_dec,
            "dec2": fmt_dec2, "money": fmt_money,
        }

        for wizard in wizards:
            sheet = workbook.add_worksheet(_("Análisis Compras"))
            filters = wizard._get_filter_summary()
            month_labels = wizard._get_month_labels()  # antiguo → reciente
            can_view_cost = wizard._can_view_product_cost()

            row = 0
            sheet.write(row, 0, "REGALARTE DE LAS AMERICAS S.A.", fmt_title)
            row += 1
            sheet.write(row, 0, _("ANÁLISIS DE VENTAS Y SUGERIDO DE COMPRAS"), fmt_title)
            row += 2

            filter_rows = [
                (_("Fecha desde"), fields.Date.to_string(filters["date_from"])),
                (_("Fecha hasta"), fields.Date.to_string(filters["date_to"])),
                (_("Meses analizados"), round(filters["analysis_months"], 1)),
                (_("Meses de cobertura"), filters["coverage_months"]),
                (_("Incluir tiempo de llegada"), _("Sí") if filters["include_lead_time"] else _("No")),
                (_("Incluir no entregado en promedio"), _("Sí") if filters["include_undelivered"] else _("No")),
                (_("Factor de servicio (Z)"), filters["service_factor"]),
                (_("Umbral coef. variación"), filters["cv_threshold"]),
                (_("Factor de exceso"), filters["excess_factor"]),
                (_("Compañías"), filters["companies"]),
                (_("Grupo de almacenes"), filters["warehouse_group"]),
                (_("Almacenes"), filters["warehouses"]),
                (_("Ventas de todos los almacenes"), _("Sí") if filters["sales_all_warehouses"] else _("No")),
                (_("Bodegas"), filters["locations"]),
                (_("Productos"), filters["products"]),
                (_("Código producto"), filters["product_code"]),
                (_("Proveedores"), filters["proveedores"]),
            ]
            for label, value in filter_rows:
                sheet.write(row, 0, label, fmt_filter_lbl)
                sheet.write(row, 1, value, fmt_filter_val)
                row += 1
            row += 1

            # Especificación de columnas: (encabezado, ancho, formato, getter, sumar en TOTAL)
            # El formato "meses_inv" se resuelve por línea (semáforo).
            columns = [
                (_("Código"), 14, "text", lambda l: l.codigo or "", False),
                (_("Descripción"), 42, "text", lambda l: l.descripcion or "", False),
            ]
            if can_view_cost:
                columns.append((_("Costo"), 11, "money", lambda l: l.costo or 0.0, False))
            columns.append((_("Precio"), 11, "money", lambda l: l.precio or 0.0, False))
            month_fields = ["mes_6", "mes_5", "mes_4", "mes_3", "mes_2", "mes_1"]
            for label, field_name in zip(month_labels, month_fields):
                columns.append((
                    label.replace(" ", "\n", 1), 9, "num",
                    (lambda l, f=field_name: l[f] or 0.0), True,
                ))
            columns += [
                (_("Total 6m"), 9, "num", lambda l: l.total_6m or 0.0, True),
                (_("Vendido en rango"), 10, "num", lambda l: l.qty_sold or 0.0, True),
                (_("No entregado"), 11, "num", lambda l: l.qty_undelivered or 0.0, True),
                (_("Prom/mes"), 10, "dec", lambda l: l.promedio_mensual or 0.0, True),
                (_("Inv. Actual"), 9, "num", lambda l: l.inv_actual or 0.0, True),
                (_("Meses Inv."), 11, "meses_inv", lambda l: l.meses_inventario or 0.0, False),
                (_("Venta atípica"), 10, "text", lambda l: _("Sí") if l.is_outlier else _("No"), False),
                (_("En OC"), 9, "dec", lambda l: l.qty_in_purchase or 0.0, True),
                (_("Plazo llegada (m)"), 10, "dec", lambda l: l.lead_time_months or 0.0, False),
                (_("Sugerido de compra"), 12, "dec", lambda l: l.suggested_purchase_qty or 0.0, True),
                (_("Sugerido menos existencias"), 14, "dec", lambda l: l.qty_to_buy or 0.0, True),
                (_("Proveedor"), 32, "text", lambda l: l.supplier_name or "", False),
            ]
            if can_view_cost:
                columns.append((_("Margen bruto %"), 9, "dec", lambda l: l.margen_pct or 0.0, False))
            columns += [
                (_("Venta valorizada 6m"), 14, "money", lambda l: l.venta_valorizada or 0.0, True),
                (_("Demanda mensual ponderada"), 11, "dec", lambda l: l.demanda_ponderada or 0.0, False),
                (_("Desv. demanda"), 10, "dec", lambda l: l.desviacion_demanda or 0.0, False),
                (_("Coef. variación"), 9, "dec2", lambda l: l.coef_variacion or 0.0, False),
                (_("Stock disponible (Inv+OC)"), 11, "num", lambda l: l.stock_disponible or 0.0, True),
                (_("Stock proyectado a llegada"), 11, "dec", lambda l: l.stock_proyectado or 0.0, False),
                (_("Stock seguridad"), 10, "dec", lambda l: l.stock_seguridad or 0.0, False),
                (_("Punto de reorden"), 10, "dec", lambda l: l.punto_reorden or 0.0, False),
                (_("Stock objetivo"), 10, "dec", lambda l: l.stock_objetivo or 0.0, False),
                (_("Necesidad neta"), 10, "dec", lambda l: l.necesidad_neta or 0.0, False),
                (_("MOQ"), 7, "num", lambda l: l.moq or 0.0, False),
                (_("Compra sugerida ajustada"), 12, "num", lambda l: l.compra_sugerida_ajustada or 0.0, True),
                (_("Cobertura (meses)"), 9, "dec", lambda l: l.cobertura_meses or 0.0, False),
                (_("Exceso unidades"), 10, "num", lambda l: l.exceso_unidades or 0.0, True),
            ]
            if can_view_cost:
                columns += [
                    (_("Valor exceso"), 14, "money", lambda l: l.valor_exceso or 0.0, True),
                    (_("Valor inventario"), 14, "money", lambda l: l.valor_inventario or 0.0, True),
                ]
            columns += [
                (_("Clase ABC"), 7, "text", lambda l: (l.clase_abc or "").upper(), False),
                (_("Riesgo / Estado"), 17, "text", lambda l: ESTADO_XLSX.get(l.estado, ""), False),
                (_("Acción recomendada"), 40, "text", lambda l: l.accion or "", False),
            ]

            header_row = row
            for col, (header, width, _kind, _getter, _sums) in enumerate(columns):
                sheet.set_column(col, col, width)
                sheet.write(header_row, col, header, fmt_header)
            sheet.set_row(header_row, 32)
            row += 1
            first_data_row = row

            for line in wizard.line_ids:
                meses = line.meses_inventario
                if meses > 12:
                    mi_fmt = fmt_red
                elif line.qty_sold == 0 and line.inv_actual > 0:
                    mi_fmt = fmt_amber
                elif 0 < meses <= 3:
                    mi_fmt = fmt_green
                else:
                    mi_fmt = fmt_dec

                for col, (_header, _width, kind, getter, _sums) in enumerate(columns):
                    value = getter(line)
                    if kind == "text":
                        sheet.write(row, col, value, fmt_text)
                    elif kind == "meses_inv":
                        sheet.write_number(row, col, value, mi_fmt)
                    else:
                        sheet.write_number(row, col, value, formats[kind])
                row += 1

            # Fila TOTAL: solo columnas donde un total tiene sentido.
            total_row = row
            sheet.write(total_row, 0, _("TOTAL"), fmt_total_lbl)
            for col, (_header, _width, _kind, _getter, sums) in enumerate(columns):
                if col == 0:
                    continue
                if sums and wizard.line_ids:
                    start = self._xl_cell(first_data_row, col)
                    end = self._xl_cell(total_row - 1, col)
                    sheet.write_formula(total_row, col, f"=SUM({start}:{end})", fmt_total_num)
                elif sums:
                    sheet.write_number(total_row, col, 0, fmt_total_num)
                else:
                    sheet.write(total_row, col, "", fmt_total_lbl)

            sheet.freeze_panes(first_data_row, 2)

            self._write_resumen_sheet(workbook, wizard, can_view_cost)

    def _write_resumen_sheet(self, workbook, wizard, can_view_cost):
        """Hoja de KPIs globales del análisis (réplica del 'Resumen Inventario')."""
        fmt_title = workbook.add_format({"bold": True, "font_size": 13})
        fmt_section = workbook.add_format({
            "bold": True, "font_size": 10, "bg_color": "#1F4E79", "font_color": "#FFFFFF",
        })
        fmt_lbl = workbook.add_format({"font_size": 9, "border": 1})
        fmt_num = workbook.add_format({"font_size": 9, "border": 1, "num_format": "#,##0", "align": "right"})
        fmt_money = workbook.add_format({"font_size": 9, "border": 1, "num_format": "#,##0.00", "align": "right"})

        lines = wizard.line_ids
        sheet = workbook.add_worksheet(_("Resumen"))
        sheet.set_column(0, 0, 38)
        sheet.set_column(1, 1, 20)

        row = 0
        sheet.write(row, 0, _("RESUMEN DE INVENTARIO Y COMPRAS"), fmt_title)
        row += 2

        sheet.write(row, 0, _("Indicadores generales"), fmt_section)
        sheet.write(row, 1, "", fmt_section)
        row += 1
        general = [
            (_("SKUs analizados"), len(lines), fmt_num),
            (_("Compra sugerida ajustada (unidades)"),
             sum(lines.mapped("compra_sugerida_ajustada")), fmt_num),
            (_("Exceso estimado (unidades)"),
             sum(lines.mapped("exceso_unidades")), fmt_num),
        ]
        if can_view_cost:
            general += [
                (_("Valor inventario actual"),
                 sum(lines.mapped("valor_inventario")), fmt_money),
                (_("Valor exceso estimado"),
                 sum(lines.mapped("valor_exceso")), fmt_money),
                (_("Compra sugerida ajustada valorizada (a costo)"),
                 sum(l.compra_sugerida_ajustada * l.costo for l in lines), fmt_money),
            ]
        for label, value, fmt in general:
            sheet.write(row, 0, label, fmt_lbl)
            sheet.write_number(row, 1, value, fmt)
            row += 1
        row += 1

        sheet.write(row, 0, _("SKUs por riesgo / estado"), fmt_section)
        sheet.write(row, 1, "", fmt_section)
        row += 1
        for key in ("quiebre", "reordenar", "inestable", "exceso", "datos_incompletos", "saludable"):
            count = len(lines.filtered(lambda l, k=key: l.estado == k))
            sheet.write(row, 0, ESTADO_XLSX[key], fmt_lbl)
            sheet.write_number(row, 1, count, fmt_num)
            row += 1
        row += 1

        sheet.write(row, 0, _("SKUs por clase ABC"), fmt_section)
        sheet.write(row, 1, "", fmt_section)
        row += 1
        for key, label in (("a", "A"), ("b", "B"), ("c", "C")):
            count = len(lines.filtered(lambda l, k=key: l.clase_abc == k))
            sheet.write(row, 0, _("Clase %s") % label, fmt_lbl)
            sheet.write_number(row, 1, count, fmt_num)
            row += 1

    @staticmethod
    def _xl_cell(row, col):
        """Referencia de celda estilo A1 (soporta columnas > Z)."""
        letters = ""
        col_num = col
        while True:
            letters = chr(ord("A") + col_num % 26) + letters
            col_num = col_num // 26 - 1
            if col_num < 0:
                break
        return f"{letters}{row + 1}"
