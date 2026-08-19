# -*- coding: utf-8 -*-
import math
from collections import defaultdict
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Nombres de meses en español (independiente del locale del servidor)
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

# Fecha de inicio de operaciones del sistema: los meses anteriores no tienen
# ventas registradas y no deben diluir el promedio mensual. Configurable vía
# ir.config_parameter 'sng_analisis_compras.operations_start_date'.
OPERATIONS_START_PARAM = "sng_analisis_compras.operations_start_date"
DEFAULT_OPERATIONS_START = "2026-04-01"

# Pesos de la demanda mensual ponderada: mes_1 (el mes de la fecha hasta) es
# el más reciente y pesa más. Índice 1..4 → columnas mes_1..mes_4.
DEMANDA_PONDERADA_PESOS = {1: 0.40, 2: 0.30, 3: 0.20, 4: 0.10}

# Acción recomendada fija por estado (réplica del Excel de compras jul-2026).
ESTADO_ACCION = {
    "datos_incompletos": "Corregir costo, precio, proveedor, plazo y MOQ",
    "quiebre": "Prioridad alta: emitir RFQ/OC y revisar alternativa local",
    "reordenar": "Comprar cantidad sugerida ajustada",
    "exceso": "Detener compra y activar plan de rotación",
    "inestable": "Revisar venta atípica y ajustar stock de seguridad",
    "saludable": "Mantener monitoreo",
}


class SngAnalisisComprasWizard(models.TransientModel):
    _name = "sng.analisis.compras.wizard"
    _description = "Wizard Análisis de Ventas y Sugerido de Compras"

    # ------------------------------------------------------------------
    # Campos
    # ------------------------------------------------------------------

    date_from = fields.Date(
        string="Fecha desde",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Fecha hasta",
        required=True,
        default=fields.Date.context_today,
        help=(
            "Además de cerrar el rango de análisis, el mes de esta fecha "
            "define la columna 'Hace 1m' del historial de 6 meses."
        ),
    )
    coverage_months = fields.Float(
        string="Meses de cobertura",
        required=True,
        default=1.0,
        digits=(12, 1),
        help="Meses de venta que debe cubrir la compra sugerida. Acepta decimales (ej. 1.5).",
    )
    company_ids = fields.Many2many(
        "res.company",
        string="Compañías",
        default=lambda self: self.env.companies,
    )
    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Almacenes",
    )
    location_ids = fields.Many2many(
        "stock.location",
        string="Bodegas",
        domain=[("usage", "=", "internal")],
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_analisis_compras_wizard_product_rel",
        "wizard_id",
        "product_id",
        string="Productos",
        domain=[("purchase_ok", "=", True), ("is_storable", "=", True)],
    )
    product_code = fields.Char(string="Código de producto")
    proveedor_ids = fields.Many2many(
        "res.partner",
        string="Proveedor(es)",
        domain=[("supplier_rank", ">", 0)],
        help="Filtra productos que tengan alguno de estos proveedores configurados. Vacío = todos.",
    )
    include_undelivered = fields.Boolean(
        string="Incluir no entregado en el promedio",
        default=False,
        help=(
            "Suma al promedio mensual la demanda no atendida: cantidad pedida "
            "en pedidos confirmados que no se entregó por falta de stock "
            "(descontando devoluciones). Desmarcado, la columna 'No entregado' "
            "es solo informativa y no altera el sugerido."
        ),
    )
    sales_all_warehouses = fields.Boolean(
        string="Ventas de todos los almacenes",
        default=True,
        help=(
            "Con el filtro de grupo/almacenes activo, el inventario y las "
            "compras en camino se limitan a los almacenes seleccionados, pero "
            "las ventas (promedio, historial y atípicas) se toman de todos "
            "los almacenes. Desmarcar para filtrar también las ventas."
        ),
    )
    only_with_sales = fields.Boolean(
        string="Solo con ventas",
        default=False,
        help="Muestra únicamente productos con ventas facturadas en el rango de análisis.",
    )
    include_lead_time = fields.Boolean(
        string="Incluir tiempo de llegada",
        default=True,
        help=(
            "Suma a los meses de cobertura el plazo de entrega del proveedor "
            "principal (campo 'Plazo de entrega' de la línea proveedor-producto, "
            "convertido a meses ÷30): mientras el pedido viaja se sigue vendiendo. "
            "Productos sin proveedor o con plazo 0 no cambian."
        ),
    )
    outlier_threshold = fields.Float(
        string="Umbral desviación estándar (σ)",
        default=2.0,
        required=True,
        help=(
            "Un producto se marca como venta atípica cuando su promedio mensual "
            "actual supera el promedio histórico más este número de desviaciones estándar."
        ),
    )
    min_history_months = fields.Integer(
        string="Meses mínimos con ventas",
        default=2,
        required=True,
        help="Mínimo de meses históricos con ventas para poder calcular la desviación estándar.",
    )
    service_factor = fields.Float(
        string="Factor de servicio (Z)",
        default=1.65,
        digits=(12, 2),
        required=True,
        help=(
            "Multiplicador de la desviación de demanda en el stock de seguridad "
            "(Z × desviación × √plazo). 1.65 ≈ nivel de servicio del 95%."
        ),
    )
    cv_threshold = fields.Float(
        string="Umbral coef. variación",
        default=0.5,
        digits=(12, 2),
        required=True,
        help=(
            "Coeficiente de variación (desviación ÷ demanda ponderada) a partir "
            "del cual el producto se marca con demanda inestable."
        ),
    )
    excess_factor = fields.Float(
        string="Factor de exceso",
        default=1.5,
        digits=(12, 2),
        required=True,
        help=(
            "El estado 'Exceso' se marca cuando el stock disponible supera el "
            "stock objetivo multiplicado por este factor."
        ),
    )
    line_ids = fields.One2many(
        "sng.analisis.compras.line",
        "wizard_id",
        string="Líneas",
    )

    # ------------------------------------------------------------------
    # Constrains
    # ------------------------------------------------------------------

    @api.constrains("date_from", "date_to", "coverage_months")
    def _check_filters(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("La fecha inicial no puede ser mayor que la fecha final."))
            if wizard.coverage_months < 0:
                raise ValidationError(_("Los meses de cobertura no pueden ser negativos."))

    @api.constrains("outlier_threshold", "min_history_months")
    def _check_outlier_config(self):
        for wizard in self:
            if wizard.outlier_threshold < 0:
                raise ValidationError(_("El umbral de desviación estándar no puede ser negativo."))
            if wizard.min_history_months < 2:
                raise ValidationError(_("Se requieren al menos 2 meses con ventas para calcular la desviación estándar."))

    @api.constrains("service_factor", "cv_threshold", "excess_factor")
    def _check_inventory_model_config(self):
        for wizard in self:
            if wizard.service_factor < 0:
                raise ValidationError(_("El factor de servicio no puede ser negativo."))
            if wizard.cv_threshold <= 0:
                raise ValidationError(_("El umbral de coeficiente de variación debe ser mayor que cero."))
            if wizard.excess_factor < 1:
                raise ValidationError(_("El factor de exceso no puede ser menor que 1."))

    # ------------------------------------------------------------------
    # Helpers de configuración / selección
    # ------------------------------------------------------------------

    def _can_view_product_cost(self):
        return self.env.user.has_group("custom_ui_security.group_view_product_cost")

    def _get_operations_start_date(self):
        param = self.env["ir.config_parameter"].sudo().get_param(
            OPERATIONS_START_PARAM, DEFAULT_OPERATIONS_START
        )
        try:
            value = fields.Date.from_string(param)
        except ValueError:
            value = None
        return value or fields.Date.from_string(DEFAULT_OPERATIONS_START)

    def _get_selected_company_ids(self):
        self.ensure_one()
        return self.company_ids.ids or self.env.companies.ids or [self.env.company.id]

    def _get_selected_warehouses(self):
        self.ensure_one()
        warehouses = self.warehouse_group_id.warehouse_ids or self.warehouse_ids
        company_ids = self._get_selected_company_ids()
        return warehouses.filtered(lambda warehouse: warehouse.company_id.id in company_ids)

    @api.onchange("warehouse_group_id")
    def _onchange_warehouse_group_id(self):
        for wizard in self:
            if wizard.warehouse_group_id:
                wizard.warehouse_ids = wizard.warehouse_group_id.warehouse_ids

    def _get_analysis_days(self):
        self.ensure_one()
        return max((self.date_to - self.date_from).days + 1, 1)

    def _get_analysis_months(self):
        """Meses del rango de análisis (días ÷ 30, informativo)."""
        self.ensure_one()
        return self._get_analysis_days() / 30.0

    def _get_avg_calculation_days(self):
        """Días usados para promediar las ventas mensuales.

        Recorta el inicio del período a la fecha de inicio de operaciones
        para que los meses sin datos no diluyan el promedio mensual.
        """
        self.ensure_one()
        date_from = max(self.date_from, self._get_operations_start_date())
        return max((self.date_to - date_from).days + 1, 1)

    def _get_avg_calculation_months(self):
        """Meses usados para promediar (días recortados ÷ 30)."""
        self.ensure_one()
        return self._get_avg_calculation_days() / 30.0

    def _get_month_starts(self):
        """Los 6 inicios de mes del historial, del más antiguo al más reciente.

        El mes más reciente es el mes de date_to.
        """
        self.ensure_one()
        ref = date(self.date_to.year, self.date_to.month, 1)
        return [ref - relativedelta(months=offset) for offset in range(5, -1, -1)]

    def _get_month_labels(self):
        """Etiquetas en español de los 6 meses, del más antiguo al más reciente."""
        return [f"{MESES_ES[m.month]} {m.year}" for m in self._get_month_starts()]

    # ------------------------------------------------------------------
    # Modelo de inventario ajustado (demanda ponderada + stock de seguridad)
    # ------------------------------------------------------------------

    def _get_partial_month_factor(self):
        """Factor para normalizar a 30 días el mes de la fecha hasta.

        Si date_to no cierra su mes calendario, las ventas de ese mes están
        incompletas y subestiman la demanda: se extrapolan a 30 días
        (qty ÷ días transcurridos × 30). Un mes completo no se ajusta.
        """
        self.ensure_one()
        month_start = self.date_to.replace(day=1)
        last_day = (month_start + relativedelta(months=1) - timedelta(days=1)).day
        if self.date_to.day >= last_day:
            return 1.0
        return 30.0 / self.date_to.day

    def _get_weighted_demand_config(self):
        """[(índice de mes 1..4, peso normalizado)] para la demanda ponderada.

        Usa los últimos 4 meses del historial (mes_1..mes_4) con pesos
        40/30/20/10. Los meses completamente anteriores al inicio de
        operaciones se excluyen (no hubo facturación y arrastrarían la
        demanda hacia abajo) y los pesos restantes se renormalizan para
        seguir sumando 1.
        """
        self.ensure_one()
        ops_start = self._get_operations_start_date()
        months = self._get_month_starts()  # antiguo → reciente
        config = [
            (index, weight)
            for index, weight in DEMANDA_PONDERADA_PESOS.items()
            if months[-index] + relativedelta(months=1) > ops_start
        ]
        total = sum(weight for _index, weight in config)
        if not total:
            return []
        return [(index, weight / total) for index, weight in config]

    def _compute_inventory_metrics(self, monthly, lead_time_months, qty_on_hand,
                                   qty_in_purchase, moq, demand_config,
                                   partial_factor):
        """Métricas del modelo ajustado para un producto.

        monthly: dict mes_1..mes_6 (mes_1 = mes de la fecha hasta).
        La desviación es la estándar poblacional de los mismos meses de la
        demanda ponderada, con el mes parcial normalizado a 30 días.
        """
        self.ensure_one()
        samples = []
        for index, weight in demand_config:
            qty = monthly.get(f"mes_{index}", 0.0)
            if index == 1:
                qty *= partial_factor
            samples.append((qty, weight))
        demanda = sum(qty * weight for qty, weight in samples)
        values = [qty for qty, _weight in samples]
        if len(values) >= 2:
            mean = sum(values) / len(values)
            desviacion = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        else:
            desviacion = 0.0
        coef_variacion = desviacion / demanda if demanda > 0 else 0.0
        stock_disponible = qty_on_hand + qty_in_purchase
        stock_proyectado = stock_disponible - demanda * lead_time_months
        stock_seguridad = self.service_factor * desviacion * math.sqrt(lead_time_months)
        punto_reorden = demanda * lead_time_months + stock_seguridad
        stock_objetivo = (
            demanda * (lead_time_months + self.coverage_months) + stock_seguridad
        )
        necesidad_neta = stock_objetivo - stock_disponible
        moq = moq if moq > 0 else 1.0
        compra_ajustada = (
            math.ceil(necesidad_neta / moq) * moq if necesidad_neta > 0 else 0.0
        )
        return {
            "demanda_ponderada": demanda,
            "desviacion_demanda": desviacion,
            "coef_variacion": coef_variacion,
            "stock_disponible": stock_disponible,
            "stock_proyectado": stock_proyectado,
            "stock_seguridad": stock_seguridad,
            "punto_reorden": punto_reorden,
            "stock_objetivo": stock_objetivo,
            "necesidad_neta": necesidad_neta,
            "moq": moq,
            "compra_sugerida_ajustada": compra_ajustada,
            "cobertura_meses": stock_disponible / demanda if demanda > 0 else 0.0,
            "exceso_unidades": max(0.0, stock_disponible - stock_objetivo),
        }

    def _get_estado(self, costo, precio, metrics):
        """Cascada de riesgo/estado, en orden de prioridad.

        Un disponible en cero con demanda negativa (devoluciones netas) no es
        quiebre: cae a reordenar/saludable según el punto de reorden.
        """
        self.ensure_one()
        if costo <= 0 or precio <= 0:
            return "datos_incompletos"
        disponible = metrics["stock_disponible"]
        if metrics["stock_proyectado"] < 0 or (
            disponible <= 0 and metrics["demanda_ponderada"] >= 0
        ):
            return "quiebre"
        if disponible <= metrics["punto_reorden"]:
            return "reordenar"
        if disponible > metrics["stock_objetivo"] * self.excess_factor:
            return "exceso"
        if metrics["coef_variacion"] > self.cv_threshold:
            return "inestable"
        return "saludable"

    @staticmethod
    def _assign_abc(rows):
        """Clase ABC por venta valorizada acumulada: A ≤80%, B ≤95%, C resto.

        El producto de mayor venta siempre es A, aunque él solo supere el 80%
        (con pocos productos el acumulado arranca sobre el umbral).
        """
        total = sum(row["venta_valorizada"] for row in rows if row["venta_valorizada"] > 0)
        accumulated = 0.0
        for row in sorted(rows, key=lambda r: -r["venta_valorizada"]):
            if total <= 0 or row["venta_valorizada"] <= 0:
                row["clase_abc"] = "c"
                continue
            first = accumulated == 0.0
            accumulated += row["venta_valorizada"]
            share = accumulated / total
            if first or share <= 0.80:
                row["clase_abc"] = "a"
            elif share <= 0.95:
                row["clase_abc"] = "b"
            else:
                row["clase_abc"] = "c"

    # ------------------------------------------------------------------
    # Dominio de productos
    # ------------------------------------------------------------------

    def _get_product_domain(self):
        self.ensure_one()
        company_ids = self._get_selected_company_ids()
        domain = [
            ("purchase_ok", "=", True),
            ("is_storable", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", company_ids),
        ]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.proveedor_ids:
            domain.append(("seller_ids.partner_id", "in", self.proveedor_ids.ids))
        if self.product_code:
            code = self.product_code.strip()
            if code:
                domain.extend(["|", ("default_code", "ilike", code), ("barcode", "ilike", code)])
        return domain

    def _get_report_products(self):
        self.ensure_one()
        return self.env["product.product"].search(self._get_product_domain(), order="default_code, name, id")

    def _get_sales_location_ids(self):
        self.ensure_one()
        if not self.location_ids:
            return []
        return self.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("id", "child_of", self.location_ids.ids),
            ]
        ).ids

    # ------------------------------------------------------------------
    # Ventas facturadas (fuente única: facturas contabilizadas)
    # ------------------------------------------------------------------

    def _execute_sales_query(self, product_ids, date_start, date_end_excl, monthly=False):
        """Ventas facturadas netas (facturas - notas de crédito) por producto.

        La atribución a almacén/ubicación de venta sigue la cadena:
        línea de factura → línea de pedido → picking de salida →
        partner_sale_location_id, con fallback a la ubicación de venta
        del cliente (sale_location_id, de sale_stock_sng).

        Con monthly=True devuelve filas (product_id, mes, qty); si no,
        (product_id, qty). Rango: date_start inclusive, date_end_excl exclusivo.
        """
        self.ensure_one()
        if not product_ids:
            return []

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        month_expr = "DATE_TRUNC('month', COALESCE(am.invoice_date, am.date))"
        select_month = f", {month_expr} AS month" if monthly else ""
        query = f"""
            SELECT
                aml.product_id{select_month},
                COALESCE(
                    SUM(
                        CASE
                            WHEN am.move_type = 'out_refund' THEN -aml.quantity
                            ELSE aml.quantity
                        END
                    ),
                    0.0
                ) AS qty_sold
            FROM account_move_line aml
            JOIN account_move am
                ON am.id = aml.move_id
            LEFT JOIN res_partner rp
                ON rp.id = am.partner_id
            LEFT JOIN LATERAL (
                SELECT
                    sol.id AS sale_line_id,
                    sol.order_id AS order_id
                FROM sale_order_line_invoice_rel rel
                JOIN sale_order_line sol
                    ON sol.id = rel.order_line_id
                WHERE rel.invoice_line_id = aml.id
                ORDER BY sol.id
                LIMIT 1
            ) sale_link ON TRUE
            LEFT JOIN sale_order so
                ON so.id = sale_link.order_id
            LEFT JOIN LATERAL (
                SELECT
                    sp2.id AS picking_id,
                    sm.partner_sale_location_id AS partner_sale_location_id
                FROM stock_move sm
                JOIN stock_picking sp2
                    ON sp2.id = sm.picking_id
                JOIN stock_picking_type spt2
                    ON spt2.id = sp2.picking_type_id
                WHERE sm.sale_line_id = sale_link.sale_line_id
                  AND spt2.code = 'outgoing'
                ORDER BY COALESCE(sp2.date_done, sp2.scheduled_date) DESC, sp2.id DESC
                LIMIT 1
            ) picking_link ON TRUE
            LEFT JOIN stock_picking sp
                ON sp.id = picking_link.picking_id
            LEFT JOIN stock_picking_type spt
                ON spt.id = sp.picking_type_id
            WHERE am.state = 'posted'
              AND am.move_type IN ('out_invoice', 'out_refund')
              AND aml.display_type = 'product'
              AND aml.product_id = ANY(%s)
              AND COALESCE(am.invoice_date, am.date) >= %s
              AND COALESCE(am.invoice_date, am.date) < %s
              AND am.company_id = ANY(%s)
        """
        params = [list(product_ids), date_start, date_end_excl, company_ids]

        if warehouses and not self.sales_all_warehouses:
            query += " AND COALESCE(so.warehouse_id, spt.warehouse_id) = ANY(%s)"
            params.append(warehouses.ids)

        sales_location_ids = self._get_sales_location_ids()
        if sales_location_ids:
            query += """
                AND COALESCE(
                    so.partner_sale_location_id,
                    picking_link.partner_sale_location_id,
                    rp.sale_location_id
                ) = ANY(%s)
            """
            params.append(sales_location_ids)

        query += f" GROUP BY aml.product_id{', ' + month_expr if monthly else ''}"
        self.env.cr.execute(query, params)
        return self.env.cr.fetchall()

    def _get_sales_qty_map(self, product_ids):
        """{product_id: qty vendida neta en el rango date_from..date_to}."""
        self.ensure_one()
        rows = self._execute_sales_query(
            product_ids, self.date_from, self.date_to + timedelta(days=1)
        )
        return {product_id: qty for product_id, qty in rows}

    def _get_monthly_breakdown_map(self, product_ids):
        """{(product_id, inicio_de_mes): qty} para los 6 meses del historial.

        El mes de date_to se incluye completo (mes calendario), igual que el
        comparativo original.
        """
        self.ensure_one()
        months = self._get_month_starts()
        rows = self._execute_sales_query(
            product_ids, months[0], months[-1] + relativedelta(months=1), monthly=True
        )
        breakdown = {}
        for product_id, month, qty in rows:
            month_date = month.date() if hasattr(month, "date") else month
            breakdown[(product_id, month_date)] = qty
        return breakdown

    def _get_monthly_sales_history_map(self, product_ids):
        """{product_id: [qty por mes]} desde inicio de operaciones hasta date_from.

        Se usa para la detección de ventas atípicas (desviación estándar).
        """
        self.ensure_one()
        rows = self._execute_sales_query(
            product_ids, self._get_operations_start_date(), self.date_from, monthly=True
        )
        history = defaultdict(list)
        for product_id, _month, qty in rows:
            history[product_id].append(qty)
        return dict(history)

    def _is_product_outlier(self, product_id, current_avg, history_map):
        self.ensure_one()
        values = history_map.get(product_id, [])
        if len(values) < max(2, self.min_history_months):
            return False
        mean = sum(values) / len(values)
        variance = sum((qty - mean) ** 2 for qty in values) / (len(values) - 1)
        std = variance ** 0.5
        if std == 0:
            return current_avg > mean
        return current_avg > mean + (self.outlier_threshold * std)

    # ------------------------------------------------------------------
    # Inventario, compras pendientes, proveedor, precios
    # ------------------------------------------------------------------

    def _get_stock_qty_map(self, product_ids):
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        domain = [
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
            ("company_id", "in", company_ids),
        ]
        if warehouses:
            domain.append(("location_id", "child_of", warehouses.mapped("lot_stock_id").ids))
        if self.location_ids:
            domain.append(("location_id", "child_of", self.location_ids.ids))

        grouped = self.env["stock.quant"].read_group(
            domain,
            ["product_id", "quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        return {
            item["product_id"][0]: item["quantity"]
            for item in grouped
            if item.get("product_id")
        }

    def _get_purchase_qty_map(self, product_ids):
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        query = """
            SELECT
                pol.product_id,
                SUM(pol.product_qty - pol.qty_received) AS qty_in_purchase
            FROM purchase_order_line pol
            JOIN purchase_order po ON po.id = pol.order_id
            JOIN stock_picking_type spt ON spt.id = po.picking_type_id
            WHERE po.state IN ('purchase', 'done')
              AND pol.qty_received < pol.product_qty
              AND pol.product_id = ANY(%s)
              AND po.company_id = ANY(%s)
        """
        params = [product_ids, company_ids]

        if warehouses:
            query += " AND spt.warehouse_id = ANY(%s)"
            params.append(warehouses.ids)

        query += " GROUP BY pol.product_id"
        self.env.cr.execute(query, params)
        return {product_id: qty for product_id, qty in self.env.cr.fetchall()}

    def _get_undelivered_qty_map(self, product_ids):
        """{product_id: qty pedida y no entregada por falta de stock}.

        Pedidos confirmados con fecha de pedido en el rango de análisis, sin
        entregas pendientes (la política comercial no genera órdenes parciales,
        así que lo no entregado es demanda perdida definitiva). Las
        devoluciones se descuentan: una pieza entregada y devuelta no es un
        faltante de stock (usar pedido − entregado a secas las contaría,
        porque la devolución reduce la cantidad entregada de la línea).
        """
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        query = """
            SELECT
                sol.product_id,
                SUM(GREATEST(sol.product_uom_qty - sol.qty_delivered
                             - COALESCE(dev.qty, 0), 0)) AS qty_undelivered
            FROM sale_order_line sol
            JOIN sale_order so
                ON so.id = sol.order_id
            LEFT JOIN res_partner rp
                ON rp.id = so.partner_id
            LEFT JOIN LATERAL (
                SELECT SUM(sm.product_qty) AS qty
                FROM stock_move sm
                JOIN stock_picking_type spt
                    ON spt.id = sm.picking_type_id
                WHERE sm.sale_line_id = sol.id
                  AND sm.state = 'done'
                  AND spt.code = 'incoming'
            ) dev ON TRUE
            WHERE so.state = 'sale'
              AND sol.display_type IS NULL
              AND sol.qty_delivered < sol.product_uom_qty
              AND sol.product_id = ANY(%s)
              AND so.company_id = ANY(%s)
              AND so.date_order >= %s
              AND so.date_order < %s
              AND NOT EXISTS (
                  SELECT 1 FROM stock_picking sp
                  WHERE sp.sale_id = so.id
                    AND sp.state NOT IN ('done', 'cancel')
              )
        """
        params = [
            list(product_ids),
            company_ids,
            self.date_from,
            self.date_to + timedelta(days=1),
        ]

        if warehouses and not self.sales_all_warehouses:
            query += " AND so.warehouse_id = ANY(%s)"
            params.append(warehouses.ids)

        sales_location_ids = self._get_sales_location_ids()
        if sales_location_ids:
            query += """
                AND COALESCE(so.partner_sale_location_id, rp.sale_location_id) = ANY(%s)
            """
            params.append(sales_location_ids)

        query += " GROUP BY sol.product_id"
        self.env.cr.execute(query, params)
        return {product_id: qty for product_id, qty in self.env.cr.fetchall()}

    def _get_vendor_map(self, products):
        """Proveedor principal por producto (menor secuencia en seller_ids)."""
        self.ensure_one()
        company_ids = set(self._get_selected_company_ids())
        vendor_map = {}
        for product in products:
            sellers = product.seller_ids.filtered(
                lambda seller: not seller.company_id or seller.company_id.id in company_ids
            )
            seller = sellers.sorted(lambda rec: (rec.sequence, rec.min_qty or 0.0, rec.id))[:1]
            vendor_map[product.id] = seller
        return vendor_map

    def _get_price_map(self, products):
        """Costo y precio actuales respetando campos dependientes de compañía.

        El costo devuelto es siempre el real: el estado, el margen y las
        valorizaciones lo necesitan internamente. Qué ve el usuario se
        decide al construir la fila (grupo de ver costos).
        """
        self.ensure_one()
        priced = products.sudo().with_company(self.env.company)
        return {
            product.id: {
                "costo": product.standard_price or 0.0,
                "precio": product.lst_price or 0.0,
            }
            for product in priced
        }

    def _get_product_report_name(self, product):
        self.ensure_one()
        return product.with_context(display_default_code=False).display_name

    # ------------------------------------------------------------------
    # Construcción de filas
    # ------------------------------------------------------------------

    def _get_report_rows(self):
        self.ensure_one()
        # Varias consultas van por SQL directo: volcar la caché ORM primero.
        self.env.flush_all()
        products = self._get_report_products()
        if not products:
            return []

        product_ids = products.ids
        analysis_months = self._get_analysis_months()
        avg_calculation_months = self._get_avg_calculation_months()
        months = self._get_month_starts()  # antiguo → reciente
        sales_map = self._get_sales_qty_map(product_ids)
        breakdown_map = self._get_monthly_breakdown_map(product_ids)
        stock_map = self._get_stock_qty_map(product_ids)
        purchase_map = self._get_purchase_qty_map(product_ids)
        undelivered_map = self._get_undelivered_qty_map(product_ids)
        history_map = self._get_monthly_sales_history_map(product_ids)
        vendor_map = self._get_vendor_map(products)
        price_map = self._get_price_map(products)
        can_view_cost = self._can_view_product_cost()
        currency_id = self.env.company.currency_id.id
        demand_config = self._get_weighted_demand_config()
        partial_factor = self._get_partial_month_factor()
        rows = []

        for product in products:
            qty_sold = sales_map.get(product.id, 0.0)
            qty_on_hand = stock_map.get(product.id, 0.0)
            qty_in_purchase = purchase_map.get(product.id, 0.0)
            qty_undelivered = undelivered_map.get(product.id, 0.0)
            avg_invoiced = qty_sold / avg_calculation_months
            # La detección de atípicas compara contra historia facturada:
            # se evalúa siempre sobre lo facturado, incluya o no el promedio
            # la demanda no atendida.
            is_outlier = self._is_product_outlier(product.id, avg_invoiced, history_map)
            if self.include_undelivered:
                avg_monthly_sales = (qty_sold + qty_undelivered) / avg_calculation_months
            else:
                avg_monthly_sales = avg_invoiced
            seller = vendor_map.get(product.id)
            # El pedido tarda 'delay' días en llegar y en ese lapso se sigue
            # vendiendo: la compra debe cubrir tránsito + cobertura pedida.
            lead_time_months = (
                (seller.delay or 0) / 30.0 if self.include_lead_time and seller else 0.0
            )
            suggested_purchase_qty = avg_monthly_sales * (
                self.coverage_months + lead_time_months
            )
            qty_to_buy = suggested_purchase_qty - qty_on_hand - qty_in_purchase
            meses_inventario = (
                qty_on_hand / avg_monthly_sales if avg_monthly_sales > 0 else 0.0
            )
            prices = price_map.get(product.id, {})
            costo = prices.get("costo", 0.0)
            precio = prices.get("precio", 0.0)
            # mes_1 = mes de date_to (months[-1]) … mes_6 = el más antiguo (months[0])
            monthly = {
                f"mes_{6 - i}": breakdown_map.get((product.id, month), 0.0)
                for i, month in enumerate(months)
            }
            total_6m = sum(monthly.values())
            metrics = self._compute_inventory_metrics(
                monthly,
                lead_time_months,
                qty_on_hand,
                qty_in_purchase,
                seller.min_qty if seller else 0.0,
                demand_config,
                partial_factor,
            )
            estado = self._get_estado(costo, precio, metrics)
            row = {
                "wizard_id": self.id,
                "product_id": product.id,
                "company_currency_id": currency_id,
                "codigo": product.default_code or product.barcode or "",
                "descripcion": self._get_product_report_name(product),
                "precio": precio,
                **monthly,
                "total_6m": total_6m,
                "qty_sold": qty_sold,
                "qty_undelivered": qty_undelivered,
                "analysis_months": analysis_months,
                "coverage_months": self.coverage_months,
                "promedio_mensual": avg_monthly_sales,
                "inv_actual": qty_on_hand,
                "meses_inventario": meses_inventario,
                "is_outlier": is_outlier,
                "qty_in_purchase": qty_in_purchase,
                "lead_time_months": lead_time_months,
                "suggested_purchase_qty": suggested_purchase_qty,
                "qty_to_buy": qty_to_buy,
                "vendor_id": seller.partner_id.id if seller else False,
                "supplier_name": seller.partner_id.display_name if seller else "",
                **metrics,
                "venta_valorizada": total_6m * precio,
                "estado": estado,
                "accion": ESTADO_ACCION[estado],
            }
            if can_view_cost:
                row["costo"] = costo
                row["margen_pct"] = ((precio - costo) / precio * 100.0) if precio else 0.0
                row["valor_inventario"] = qty_on_hand * costo
                row["valor_exceso"] = metrics["exceso_unidades"] * costo
            rows.append(row)

        if self.only_with_sales:
            rows = [r for r in rows if r["qty_sold"] > 0]
        # La clase ABC se asigna sobre el universo final de filas del reporte.
        self._assign_abc(rows)
        return rows

    def _refresh_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        rows = self._get_report_rows()
        if rows:
            self.env["sng.analisis.compras.line"].create(rows)
        return rows

    def _get_filter_summary(self):
        self.ensure_one()
        warehouses = self._get_selected_warehouses()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "analysis_months": self._get_analysis_months(),
            "coverage_months": self.coverage_months,
            "include_lead_time": self.include_lead_time,
            "service_factor": self.service_factor,
            "cv_threshold": self.cv_threshold,
            "excess_factor": self.excess_factor,
            "companies": ", ".join(self.company_ids.mapped("display_name")) or _("Todas"),
            "warehouse_group": self.warehouse_group_id.display_name or _("Ninguno"),
            "warehouses": ", ".join(warehouses.mapped("display_name")) or _("Todos"),
            "sales_all_warehouses": self.sales_all_warehouses,
            "include_undelivered": self.include_undelivered,
            "locations": ", ".join(self.location_ids.mapped("display_name")) or _("Todas"),
            "products": ", ".join(self.product_ids.mapped("display_name")) or _("Todos"),
            "product_code": self.product_code or _("Todos"),
            "proveedores": ", ".join(self.proveedor_ids.mapped("display_name")) or _("Todos"),
        }

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def action_view_report(self):
        self.ensure_one()
        self._refresh_lines()
        action = self.env.ref("sng_analisis_compras.action_sng_analisis_compras_line").read()[0]
        action["domain"] = [("wizard_id", "=", self.id)]
        action["context"] = {"default_wizard_id": self.id}
        ref = self.date_to
        action["name"] = f"Análisis de Compras — {MESES_ES[ref.month]} {ref.year}"
        return action

    def action_export_xlsx(self):
        self.ensure_one()
        self._refresh_lines()
        return self.env.ref("sng_analisis_compras.action_sng_analisis_compras_xlsx").report_action(self)


class SngAnalisisComprasLine(models.TransientModel):
    _name = "sng.analisis.compras.line"
    _description = "Línea Análisis de Compras"
    _order = "qty_to_buy desc, qty_sold desc, descripcion asc, id asc"

    wizard_id = fields.Many2one(
        "sng.analisis.compras.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        readonly=True,
    )
    codigo = fields.Char(string="Código", readonly=True)
    descripcion = fields.Char(string="Descripción", readonly=True)
    costo = fields.Monetary(
        string="Costo",
        currency_field="company_currency_id",
        readonly=True,
        groups="custom_ui_security.group_view_product_cost",
    )
    precio = fields.Monetary(
        string="Precio",
        currency_field="company_currency_id",
        readonly=True,
    )
    mes_6 = fields.Float(string="Hace 6m", digits="Product Unit of Measure", readonly=True)
    mes_5 = fields.Float(string="Hace 5m", digits="Product Unit of Measure", readonly=True)
    mes_4 = fields.Float(string="Hace 4m", digits="Product Unit of Measure", readonly=True)
    mes_3 = fields.Float(string="Hace 3m", digits="Product Unit of Measure", readonly=True)
    mes_2 = fields.Float(string="Hace 2m", digits="Product Unit of Measure", readonly=True)
    mes_1 = fields.Float(string="Hace 1m", digits="Product Unit of Measure", readonly=True)
    total_6m = fields.Float(string="Total 6m", digits="Product Unit of Measure", readonly=True)
    qty_sold = fields.Float(
        string="Vendido en rango",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_undelivered = fields.Float(
        string="No entregado",
        digits="Product Unit of Measure",
        readonly=True,
        help=(
            "Cantidad pedida en el rango que no se entregó por falta de stock "
            "(pedidos confirmados, sin contar devoluciones)."
        ),
    )
    analysis_months = fields.Float(string="Meses analizados", digits=(12, 1), readonly=True)
    coverage_months = fields.Float(string="Meses de cobertura", digits=(12, 1), readonly=True)
    promedio_mensual = fields.Float(
        string="Prom/mes",
        digits=(12, 1),
        readonly=True,
    )
    inv_actual = fields.Float(
        string="Inv. Actual",
        digits="Product Unit of Measure",
        readonly=True,
    )
    meses_inventario = fields.Float(string="Meses Inv.", digits=(12, 1), readonly=True)
    is_outlier = fields.Boolean(string="Venta atípica", readonly=True)
    qty_in_purchase = fields.Float(
        string="En órdenes de compra",
        digits="Product Unit of Measure",
        readonly=True,
    )
    lead_time_months = fields.Float(
        string="Plazo llegada (meses)",
        digits=(12, 1),
        readonly=True,
        help="Plazo de entrega del proveedor principal en meses (delay ÷ 30), sumado a la cobertura en el sugerido.",
    )
    suggested_purchase_qty = fields.Float(
        string="Sugerido de compra",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_to_buy = fields.Float(
        string="Sugerido menos existencias",
        digits="Product Unit of Measure",
        readonly=True,
    )
    vendor_id = fields.Many2one("res.partner", string="Proveedor", readonly=True)
    supplier_name = fields.Char(string="Nombre proveedor", readonly=True)

    # --- Modelo de inventario ajustado (demanda ponderada + stock seguridad) ---
    margen_pct = fields.Float(
        string="Margen bruto %",
        digits=(12, 1),
        readonly=True,
        groups="custom_ui_security.group_view_product_cost",
        help="(Precio − Costo) ÷ Precio × 100.",
    )
    venta_valorizada = fields.Monetary(
        string="Venta valorizada 6m",
        currency_field="company_currency_id",
        readonly=True,
        help="Total 6m × precio de venta actual. Base de la clasificación ABC.",
    )
    demanda_ponderada = fields.Float(
        string="Demanda mensual ponderada",
        digits=(12, 1),
        readonly=True,
        help=(
            "Últimos 4 meses con pesos 40/30/20/10 (el más reciente pesa más). "
            "El mes parcial se normaliza a 30 días y los meses previos al "
            "inicio de operaciones se excluyen."
        ),
    )
    desviacion_demanda = fields.Float(
        string="Desv. demanda",
        digits=(12, 1),
        readonly=True,
        help="Desviación estándar poblacional de los mismos meses de la demanda ponderada.",
    )
    coef_variacion = fields.Float(
        string="Coef. variación",
        digits=(12, 2),
        readonly=True,
        help="Desviación ÷ demanda ponderada. Sobre el umbral = demanda inestable.",
    )
    stock_disponible = fields.Float(
        string="Stock disponible",
        digits="Product Unit of Measure",
        readonly=True,
        help="Inventario actual + en órdenes de compra.",
    )
    stock_proyectado = fields.Float(
        string="Stock proyectado a llegada",
        digits=(12, 1),
        readonly=True,
        help=(
            "Stock disponible − demanda ponderada × plazo de llegada. Negativo "
            "= se agota antes de que llegue un pedido hecho hoy."
        ),
    )
    stock_seguridad = fields.Float(
        string="Stock seguridad",
        digits=(12, 1),
        readonly=True,
        help="Z × desviación × √plazo: colchón contra la variabilidad durante el tránsito.",
    )
    punto_reorden = fields.Float(
        string="Punto de reorden",
        digits=(12, 1),
        readonly=True,
        help="Demanda ponderada × plazo + stock de seguridad. Disponible por debajo = hora de pedir.",
    )
    stock_objetivo = fields.Float(
        string="Stock objetivo",
        digits=(12, 1),
        readonly=True,
        help="Demanda ponderada × (plazo + cobertura) + stock de seguridad.",
    )
    necesidad_neta = fields.Float(
        string="Necesidad neta",
        digits=(12, 1),
        readonly=True,
        help="Stock objetivo − stock disponible.",
    )
    moq = fields.Float(
        string="MOQ",
        digits="Product Unit of Measure",
        readonly=True,
        help=(
            "Cantidad mínima del proveedor principal (mínimo 1). La compra "
            "ajustada se redondea hacia arriba a múltiplos de este valor."
        ),
    )
    compra_sugerida_ajustada = fields.Float(
        string="Compra sugerida ajustada",
        digits="Product Unit of Measure",
        readonly=True,
        help="Necesidad neta redondeada hacia arriba al MOQ; cero si no hay necesidad.",
    )
    cobertura_meses = fields.Float(
        string="Cobertura (meses)",
        digits=(12, 1),
        readonly=True,
        help="Stock disponible ÷ demanda ponderada.",
    )
    exceso_unidades = fields.Float(
        string="Exceso unidades",
        digits="Product Unit of Measure",
        readonly=True,
        help="Stock disponible que supera el stock objetivo (mínimo 0).",
    )
    valor_exceso = fields.Monetary(
        string="Valor exceso",
        currency_field="company_currency_id",
        readonly=True,
        groups="custom_ui_security.group_view_product_cost",
        help="Exceso de unidades × costo.",
    )
    valor_inventario = fields.Monetary(
        string="Valor inventario",
        currency_field="company_currency_id",
        readonly=True,
        groups="custom_ui_security.group_view_product_cost",
        help="Inventario actual × costo.",
    )
    clase_abc = fields.Selection(
        [("a", "A"), ("b", "B"), ("c", "C")],
        string="Clase ABC",
        readonly=True,
        help="Por venta valorizada acumulada: A hasta el 80%, B hasta el 95%, C el resto.",
    )
    estado = fields.Selection(
        [
            ("datos_incompletos", "Datos incompletos"),
            ("quiebre", "Quiebre proyectado"),
            ("reordenar", "Reordenar"),
            ("exceso", "Exceso"),
            ("inestable", "Demanda inestable"),
            ("saludable", "Saludable"),
        ],
        string="Riesgo / Estado",
        readonly=True,
    )
    accion = fields.Char(string="Acción recomendada", readonly=True)

    def action_open_product(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "product.product",
            "res_id": self.product_id.id,
            "view_mode": "form",
            "target": "current",
        }
