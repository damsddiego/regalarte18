# -*- coding: utf-8 -*-
import io
import json
from datetime import date

from odoo import api, fields, models
from odoo.tools import json_default

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter

# Nombres de meses en español (independiente del locale del servidor)
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


class SngComparativoWizard(models.TransientModel):
    _name = "sng.comparativo.wizard"
    _description = "Wizard Comparativo de Ventas"

    fecha_referencia = fields.Date(
        string="Fecha de referencia",
        required=True,
        default=fields.Date.today,
        help=(
            "El mes de esta fecha se toma como 'Hace 1 mes' (mes actual). "
            "El reporte cubre los 6 meses anteriores inclusive."
        ),
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Bodega(s)",
        help="Filtra inventario a bodegas seleccionadas. Vacío = todas.",
    )
    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
        help="Usa los almacenes configurados en el grupo para filtrar el inventario.",
    )
    proveedor_ids = fields.Many2many(
        "res.partner",
        string="Proveedor(es)",
        domain=[("supplier_rank", ">", 0)],
        help="Filtra por proveedor principal del producto. Vacío = todos.",
    )
    solo_con_ventas = fields.Boolean(
        string="Solo productos con ventas",
        default=False,
        help="Muestra únicamente productos con al menos 1 venta en los 6 meses.",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _can_view_product_cost(self):
        return self.env.user.has_group("custom_ui_security.group_view_product_cost")

    def _get_selected_warehouses(self):
        self.ensure_one()
        return self.warehouse_group_id.warehouse_ids or self.warehouse_ids

    @api.onchange("warehouse_group_id")
    def _onchange_warehouse_group_id(self):
        for wizard in self:
            if wizard.warehouse_group_id:
                wizard.warehouse_ids = wizard.warehouse_group_id.warehouse_ids

    def _get_location_ids(self):
        domain = [("usage", "=", "internal")]
        warehouses = self._get_selected_warehouses()
        if warehouses:
            parent_ids = warehouses.mapped("view_location_id").ids
            domain = [("usage", "=", "internal"), ("id", "child_of", parent_ids)]
        return self.env["stock.location"].search(domain).ids

    def _month_labels(self):
        """Etiquetas de los 6 meses, del más antiguo al más reciente.

        Formato solicitado: '<posición> <Mes> <Año>', donde la posición va de
        6 (hace 6 meses) a 1 (mes de referencia). Ej: '6 Noviembre 2025'.
        """
        ref = self.fecha_referencia
        labels = []
        for offset in range(5, -1, -1):
            month = ref.month - offset
            year = ref.year
            while month < 1:
                month += 12
                year -= 1
            labels.append(f"{offset + 1} {MESES_ES[month]} {year}")
        return labels

    def _build_list_arch(self):
        """Reconstruye el arch de la vista lista con los nombres de meses
        en español según la fecha de referencia. mes_6=más antiguo … mes_1=más reciente.
        """
        from odoo.tools import html_escape

        labels = self._month_labels()  # oldest→newest
        meses_cols = ["mes_6", "mes_5", "mes_4", "mes_3", "mes_2", "mes_1"]
        mes_fields = "\n".join(
            f'<field name="{col}" string="{html_escape(labels[i])}" sum="Total"/>'
            for i, col in enumerate(meses_cols)
        )
        cost_field = (
            '<field name="costo" string="Costo" optional="show" '
            'groups="custom_ui_security.group_view_product_cost"/>'
        )
        return f"""
            <list string="Comparativo de Ventas"
                  decoration-danger="meses_inventario &gt; 12"
                  decoration-warning="total_6m == 0 and inv_actual &gt; 0"
                  decoration-success="meses_inventario &gt; 0 and meses_inventario &lt;= 3"
                  create="false" delete="false" import="false">
                <field name="codigo" optional="show" string="Código"/>
                <field name="descripcion" string="Descripción"/>
                {cost_field}
                <field name="precio" string="Precio" optional="show"/>
                {mes_fields}
                <field name="total_6m"          string="Total 6m"   sum="Total"/>
                <field name="promedio_mensual"   string="Prom/mes"   avg="Prom"/>
                <field name="inv_actual"         string="Inv. Actual" sum="Total"/>
                <field name="meses_inventario"   string="Meses Inv." avg="Prom"/>
                <field name="proveedor"          string="Proveedor"  optional="show"/>
                <field name="product_id"         string="Producto"   optional="hide"/>
                <field name="company_currency_id" optional="hide" column_invisible="1"/>
            </list>
        """

    # ------------------------------------------------------------------
    # SQL
    # ------------------------------------------------------------------

    def _run_query(self):
        ref = self.fecha_referencia
        location_ids = self._get_location_ids()
        proveedor_ids = self.proveedor_ids.ids

        params = {"ref": str(ref)}

        # Inventory location filter (injected inside the CTE)
        if location_ids:
            params["location_ids"] = tuple(location_ids)
            loc_filter = "AND sq.location_id IN %(location_ids)s"
        else:
            loc_filter = ""

        # Supplier filter (injected as a condition on the outer query)
        if proveedor_ids:
            params["proveedor_ids"] = tuple(proveedor_ids)
            prov_filter = """
                AND EXISTS (
                    SELECT 1 FROM product_supplierinfo ps_f
                    WHERE ps_f.product_tmpl_id = pt.id
                      AND ps_f.partner_id IN %(proveedor_ids)s
                )
            """
        else:
            prov_filter = ""

        # Solo con ventas filter (wraps the whole query as a subquery)
        ventas_filter = "AND total_6m > 0" if self.solo_con_ventas else ""

        query = f"""
            SELECT *
            FROM (
                WITH ventas AS (
                    SELECT
                        sol.product_id,
                        date_trunc('month', so.date_order::date) AS mes,
                        SUM(sol.product_uom_qty)                 AS qty
                    FROM sale_order_line sol
                    JOIN sale_order so ON so.id = sol.order_id
                    WHERE so.state IN ('sale', 'done')
                      AND so.date_order >= (date_trunc('month', %(ref)s::date) - INTERVAL '5 months')
                      AND so.date_order  < (date_trunc('month', %(ref)s::date) + INTERVAL '1 month')
                      AND sol.product_id IS NOT NULL
                    GROUP BY sol.product_id, date_trunc('month', so.date_order::date)
                ),
                inventario AS (
                    SELECT sq.product_id, SUM(sq.quantity) AS qty_inv
                    FROM stock_quant sq
                    JOIN stock_location sl ON sl.id = sq.location_id
                    WHERE sl.usage = 'internal'
                    {loc_filter}
                    GROUP BY sq.product_id
                ),
                proveedor AS (
                    SELECT DISTINCT ON (ps.product_tmpl_id)
                        ps.product_tmpl_id,
                        rp.name AS nombre
                    FROM product_supplierinfo ps
                    JOIN res_partner rp ON rp.id = ps.partner_id
                    ORDER BY ps.product_tmpl_id, ps.sequence ASC, ps.id ASC
                )
                SELECT
                    pp.id                                                          AS product_id,
                    COALESCE(pp.default_code, '')                                  AS codigo,
                    COALESCE(pt.name->>'es_CR', pt.name->>'en_US', '')            AS descripcion,
                    COALESCE(v6.qty, 0)                                            AS mes_6,
                    COALESCE(v5.qty, 0)                                            AS mes_5,
                    COALESCE(v4.qty, 0)                                            AS mes_4,
                    COALESCE(v3.qty, 0)                                            AS mes_3,
                    COALESCE(v2.qty, 0)                                            AS mes_2,
                    COALESCE(v1.qty, 0)                                            AS mes_1,
                    COALESCE(v6.qty,0)+COALESCE(v5.qty,0)+COALESCE(v4.qty,0)
                        +COALESCE(v3.qty,0)+COALESCE(v2.qty,0)+COALESCE(v1.qty,0) AS total_6m,
                    -- Divisor = meses con ventas reales (mínimo 1 para evitar div/0)
                    (CASE WHEN COALESCE(v6.qty,0)>0 THEN 1 ELSE 0 END
                    +CASE WHEN COALESCE(v5.qty,0)>0 THEN 1 ELSE 0 END
                    +CASE WHEN COALESCE(v4.qty,0)>0 THEN 1 ELSE 0 END
                    +CASE WHEN COALESCE(v3.qty,0)>0 THEN 1 ELSE 0 END
                    +CASE WHEN COALESCE(v2.qty,0)>0 THEN 1 ELSE 0 END
                    +CASE WHEN COALESCE(v1.qty,0)>0 THEN 1 ELSE 0 END)            AS meses_con_ventas,
                    CASE
                        WHEN (CASE WHEN COALESCE(v6.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v5.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v4.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v3.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v2.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v1.qty,0)>0 THEN 1 ELSE 0 END) > 0
                        THEN (COALESCE(v6.qty,0)+COALESCE(v5.qty,0)+COALESCE(v4.qty,0)
                             +COALESCE(v3.qty,0)+COALESCE(v2.qty,0)+COALESCE(v1.qty,0))::numeric
                             / NULLIF((CASE WHEN COALESCE(v6.qty,0)>0 THEN 1 ELSE 0 END
                                      +CASE WHEN COALESCE(v5.qty,0)>0 THEN 1 ELSE 0 END
                                      +CASE WHEN COALESCE(v4.qty,0)>0 THEN 1 ELSE 0 END
                                      +CASE WHEN COALESCE(v3.qty,0)>0 THEN 1 ELSE 0 END
                                      +CASE WHEN COALESCE(v2.qty,0)>0 THEN 1 ELSE 0 END
                                      +CASE WHEN COALESCE(v1.qty,0)>0 THEN 1 ELSE 0 END), 0)
                        ELSE 0
                    END                                                            AS promedio_mensual,
                    COALESCE(inv.qty_inv, 0)                                       AS inv_actual,
                    CASE
                        WHEN (CASE WHEN COALESCE(v6.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v5.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v4.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v3.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v2.qty,0)>0 THEN 1 ELSE 0 END
                             +CASE WHEN COALESCE(v1.qty,0)>0 THEN 1 ELSE 0 END) > 0
                        THEN COALESCE(inv.qty_inv, 0)
                             / ((COALESCE(v6.qty,0)+COALESCE(v5.qty,0)+COALESCE(v4.qty,0)
                                +COALESCE(v3.qty,0)+COALESCE(v2.qty,0)+COALESCE(v1.qty,0))::numeric
                                / NULLIF((CASE WHEN COALESCE(v6.qty,0)>0 THEN 1 ELSE 0 END
                                         +CASE WHEN COALESCE(v5.qty,0)>0 THEN 1 ELSE 0 END
                                         +CASE WHEN COALESCE(v4.qty,0)>0 THEN 1 ELSE 0 END
                                         +CASE WHEN COALESCE(v3.qty,0)>0 THEN 1 ELSE 0 END
                                         +CASE WHEN COALESCE(v2.qty,0)>0 THEN 1 ELSE 0 END
                                         +CASE WHEN COALESCE(v1.qty,0)>0 THEN 1 ELSE 0 END), 0))
                        ELSE 0
                    END                                                            AS meses_inventario,
                    COALESCE(prov.nombre, '')                                      AS proveedor
                FROM product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN ventas v1 ON v1.product_id = pp.id
                    AND v1.mes = date_trunc('month', %(ref)s::date)
                LEFT JOIN ventas v2 ON v2.product_id = pp.id
                    AND v2.mes = date_trunc('month', %(ref)s::date) - INTERVAL '1 month'
                LEFT JOIN ventas v3 ON v3.product_id = pp.id
                    AND v3.mes = date_trunc('month', %(ref)s::date) - INTERVAL '2 months'
                LEFT JOIN ventas v4 ON v4.product_id = pp.id
                    AND v4.mes = date_trunc('month', %(ref)s::date) - INTERVAL '3 months'
                LEFT JOIN ventas v5 ON v5.product_id = pp.id
                    AND v5.mes = date_trunc('month', %(ref)s::date) - INTERVAL '4 months'
                LEFT JOIN ventas v6 ON v6.product_id = pp.id
                    AND v6.mes = date_trunc('month', %(ref)s::date) - INTERVAL '5 months'
                LEFT JOIN inventario inv ON inv.product_id = pp.id
                LEFT JOIN proveedor  prov ON prov.product_tmpl_id = pt.id
                WHERE pt.active = TRUE
                  AND pp.active = TRUE
                  AND pt.type NOT IN ('service', 'combo')
                  {prov_filter}
            ) sub
            WHERE 1=1
            {ventas_filter}
            ORDER BY descripcion ASC
        """

        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()
        return self._add_product_prices(rows)

    def _add_product_prices(self, rows):
        """Agrega costo y precio actuales respetando campos dependientes de compañía."""
        product_ids = [row["product_id"] for row in rows if row.get("product_id")]
        products = self.env["product.product"].sudo().with_company(self.env.company).browse(product_ids)
        can_view_cost = self._can_view_product_cost()
        price_by_product = {
            product.id: {
                "costo": (product.standard_price or 0.0) if can_view_cost else 0.0,
                "precio": product.lst_price or 0.0,
            }
            for product in products
        }
        for row in rows:
            prices = price_by_product.get(row["product_id"], {})
            row["costo"] = prices.get("costo", 0.0)
            row["precio"] = prices.get("precio", 0.0)
        return rows

    # ------------------------------------------------------------------
    # Botón: Generar
    # ------------------------------------------------------------------

    def action_generar(self):
        LineMdl = self.env["sng.comparativo.line"]
        LineMdl.search([("create_uid", "=", self.env.uid)]).unlink()

        rows = self._run_query()
        can_view_cost = self._can_view_product_cost()
        values_list = []
        for r in rows:
            values = {
                "product_id": r["product_id"],
                "company_currency_id": self.env.company.currency_id.id,
                "codigo":      r["codigo"],
                "descripcion": r["descripcion"],
                "precio":      r["precio"],
                "mes_6":       r["mes_6"],
                "mes_5":       r["mes_5"],
                "mes_4":       r["mes_4"],
                "mes_3":       r["mes_3"],
                "mes_2":       r["mes_2"],
                "mes_1":       r["mes_1"],
                "total_6m":    r["total_6m"],
                "promedio_mensual": r["promedio_mensual"],
                "inv_actual":  r["inv_actual"],
                "meses_inventario": r["meses_inventario"],
                "proveedor":   r["proveedor"],
            }
            if can_view_cost:
                values["costo"] = r["costo"]
            values_list.append(values)
        LineMdl.create(values_list)

        # Renombra dinámicamente las columnas de meses con su nombre en español
        # (mes_6 = más antiguo … mes_1 = mes de referencia) según la fecha elegida.
        view = self.env.ref("sng_comparativo_ventas.view_sng_comparativo_line_list")
        view.sudo().write({"arch": self._build_list_arch()})

        ref = self.fecha_referencia
        return {
            "type": "ir.actions.act_window",
            "name": f"Comparativo de Ventas — {MESES_ES[ref.month]} {ref.year}",
            "res_model": "sng.comparativo.line",
            "view_mode": "list",
            "domain": [("create_uid", "=", self.env.uid)],
            "context": {"search_default_group_by_proveedor": 0},
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Botón: Exportar XLS
    # ------------------------------------------------------------------

    def action_exportar_xls(self):
        data = {
            "wizard_id": self.id,
            "fecha_referencia": str(self.fecha_referencia),
        }
        return {
            "type": "ir.actions.report",
            "data": {
                "model": self._name,
                "options": json.dumps(data, default=json_default),
                "output_format": "xlsx",
                "report_name": f"Comparativo_Ventas_{self.fecha_referencia}",
            },
            "report_type": "comparativo_xlsx",
        }

    # ------------------------------------------------------------------
    # Generación Excel (llamado desde el controller)
    # ------------------------------------------------------------------

    def get_xlsx_report(self, data, response):
        wizard = self.browse(data["wizard_id"])
        rows = wizard._run_query()
        month_labels = wizard._month_labels()

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {"in_memory": True})
        ws = wb.add_worksheet("Comparativo Ventas")

        # -- Formatos --
        fmt_title = wb.add_format({
            "bold": True, "font_size": 13, "align": "center", "valign": "vcenter",
        })
        fmt_header = wb.add_format({
            "bold": True, "font_size": 9, "align": "center", "valign": "vcenter",
            "bg_color": "#1F4E79", "font_color": "#FFFFFF",
            "border": 1, "text_wrap": True,
        })
        fmt_text  = wb.add_format({"font_size": 8, "align": "left",  "border": 1})
        fmt_num   = wb.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0"})
        fmt_dec   = wb.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0.0"})
        fmt_money = wb.add_format({"font_size": 8, "align": "right", "border": 1, "num_format": "#,##0.00"})
        fmt_red   = wb.add_format({
            "font_size": 8, "align": "right", "border": 1,
            "num_format": "#,##0.0", "bg_color": "#FFCCCC",
        })
        fmt_amber = wb.add_format({
            "font_size": 8, "align": "right", "border": 1,
            "num_format": "#,##0.0", "bg_color": "#FFE5CC",
        })
        fmt_green = wb.add_format({
            "font_size": 8, "align": "right", "border": 1,
            "num_format": "#,##0.0", "bg_color": "#CCFFCC",
        })
        fmt_total_lbl = wb.add_format({
            "bold": True, "font_size": 8, "align": "left",
            "border": 1, "bg_color": "#D9D9D9",
        })
        fmt_total_num = wb.add_format({
            "bold": True, "font_size": 8, "align": "right",
            "border": 1, "num_format": "#,##0", "bg_color": "#D9D9D9",
        })

        ref = wizard.fecha_referencia
        can_view_cost = wizard._can_view_product_cost()

        # -- Encabezado --
        last_col = "O" if can_view_cost else "N"
        ws.merge_range(f"A1:{last_col}1", "REGALARTE DE LAS AMERICAS S.A.", fmt_title)
        ws.merge_range(f"A2:{last_col}2", "REPORTE COMPARATIVO DE VENTAS", fmt_title)
        ws.merge_range(
            f"A3:{last_col}3",
            f"Fecha de referencia: {ref.strftime('%d/%m/%Y')}  |  "
            f"Período: {month_labels[0]} – {month_labels[5]}",
            fmt_title,
        )

        # -- Cabeceras de columnas --
        # month_labels viene como ['6 Noviembre 2025', ... , '1 Abril 2026'] (antiguo→reciente)
        headers = [
            "Código", "Descripción",
            *(["Costo"] if can_view_cost else []),
            "Precio",
            month_labels[0].replace(" ", "\n", 1),
            month_labels[1].replace(" ", "\n", 1),
            month_labels[2].replace(" ", "\n", 1),
            month_labels[3].replace(" ", "\n", 1),
            month_labels[4].replace(" ", "\n", 1),
            month_labels[5].replace(" ", "\n", 1),
            "Total 6m", "Prom/mes", "Inv. Actual", "Meses Inv.", "Proveedor",
        ]
        col_widths = [
            14, 42,
            *([11] if can_view_cost else []),
            11, 9, 9, 9, 9, 9, 9, 10, 9, 11, 10, 32,
        ]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            ws.set_column(col, col, w)
            ws.write(3, col, h, fmt_header)
        ws.set_row(3, 32)

        # -- Filas de datos --
        for row_idx, r in enumerate(rows, start=4):
            meses = r["meses_inventario"]
            if meses > 12:
                mi_fmt = fmt_red
            elif r["total_6m"] == 0 and r["inv_actual"] > 0:
                mi_fmt = fmt_amber
            elif 0 < meses <= 3:
                mi_fmt = fmt_green
            else:
                mi_fmt = fmt_dec

            ws.write(row_idx, 0,  r["codigo"],       fmt_text)
            ws.write(row_idx, 1,  r["descripcion"],  fmt_text)
            col = 2
            if can_view_cost:
                ws.write(row_idx, col, r["costo"], fmt_money)
                col += 1
            ws.write(row_idx, col, r["precio"], fmt_money)
            col += 1
            for key in ("mes_6", "mes_5", "mes_4", "mes_3", "mes_2", "mes_1", "total_6m"):
                ws.write(row_idx, col, r[key], fmt_num)
                col += 1
            ws.write(row_idx, col, r["promedio_mensual"], fmt_dec)
            col += 1
            ws.write(row_idx, col, r["inv_actual"], fmt_num)
            col += 1
            ws.write(row_idx, col, meses, mi_fmt)
            col += 1
            ws.write(row_idx, col, r["proveedor"], fmt_text)

        # -- Fila de totales --
        total_row = len(rows) + 4
        ws.write(total_row, 0, "TOTAL", fmt_total_lbl)
        ws.write(total_row, 1, "",      fmt_total_lbl)
        first_total_col = 4 if can_view_cost else 3
        for col in range(2, first_total_col):
            ws.write(total_row, col, "", fmt_total_lbl)
        for col in range(first_total_col, len(headers) - 1):
            col_letter = chr(ord("A") + col)
            ws.write_formula(
                total_row, col,
                f"=SUM({col_letter}5:{col_letter}{total_row})",
                fmt_total_num,
            )
        ws.write(total_row, len(headers) - 1, "", fmt_total_lbl)

        ws.freeze_panes(4, 2)

        wb.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
