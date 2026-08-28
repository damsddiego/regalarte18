# -*- coding: utf-8 -*-
import json
import logging

import requests
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Precio por millón de tokens (entrada, salida) en USD
PRICING = {
    'claude-opus-4-8': (5.0, 25.0),
    'claude-sonnet-5': (3.0, 15.0),
    'claude-haiku-4-5': (1.0, 5.0),
    'deepseek-v4-flash': (0.14, 0.28),
    'deepseek-v4-pro': (0.435, 0.87),
}

SYSTEM_PROMPT = """Eres un analista financiero senior de una empresa comercial costarricense (venta y \
distribución de mercadería, facturación electrónica, clientes con crédito). Recibirás un JSON con los \
indicadores del negocio: ventas mensuales, ventas por vendedor asignado, antigüedad de cuentas por \
cobrar (morosidad) y valor de inventario por categoría. Los montos están en colones costarricenses (CRC) \
salvo que se indique otra moneda.

También recibirás datos de cobranza: cobrado por mes (pagos de clientes aplicados a cuentas por
cobrar), cobrado vs facturado del período y el DSO (días promedio de cobro estimado).

Sobre inventario recibirás dos bloques: `inventario_valoracion_global` (valoración contable de
toda la empresa; puede venir negativa por problemas de datos con stock negativo — si es así,
señálalo como problema de datos a corregir) e `inventario_almacen_principal` (almacén principal:
valor a costo por categoría, meses de cobertura = stock ÷ venta promedio mensual en unidades,
top de productos más vendidos con margen aproximado, productos en riesgo de faltante —
cobertura < 1 mes — y productos sin movimiento).

Recibirás además un bloque `gestion_cobranza` enfocado en liquidez: lista priorizada de clientes
a gestionar HOY (saldo vencido, días de atraso, fecha del último pago), facturado vs cobrado por
mes con tasa de recuperación, y las facturas vencidas más grandes.

Tus recomendaciones deben ser accionables y priorizadas, por ejemplo: qué productos comprar YA
(riesgo de faltante en los más vendidos), qué categorías NO comprar (cobertura > 12 meses),
qué liquidar o promocionar (sin movimiento / sobre-stock), a qué clientes gestionar cobro
primero (morosos grandes y viejos), y qué vendedores o categorías necesitan atención. Cuando el
margen aproximado de un producto muy vendido sea bajo o negativo, señálalo.

En cobranza sé muy concreto para mejorar la liquidez: indica a qué clientes llamar o notificar
primero (nombre y monto), a cuáles conviene suspender crédito o pasar a gestión formal (mucho
atraso y sin pagos recientes), cuánto se recuperaría de caja gestionando los 5 primeros, y si la
tasa de recuperación (cobrado ÷ facturado) de algún mes es baja, señálalo.

Tu tarea: producir un análisis ejecutivo corto y accionable para la gerencia, en español,
enfocado en el período de análisis indicado en el JSON (campo periodo_meses).

Formato de salida: responde ÚNICAMENTE con un fragmento HTML (sin <html> ni <body>) usando solo estas \
etiquetas: <h4>, <p>, <ul>, <li>, <strong>, <em>. Estructura:
<h4>Resumen ejecutivo</h4> (2-4 frases con lo más importante)
<h4>Alertas</h4> (lista de riesgos concretos: caídas de venta, clientes morosos críticos, concentración, etc.)
<h4>Recomendaciones</h4> (lista de 3-6 acciones concretas y priorizadas, con cifras cuando aplique)

Sé específico: nombra clientes, vendedores, categorías y montos del JSON. No inventes datos que no estén \
en el JSON. Si un dato viene vacío o en cero, ignóralo o menciónalo como falta de información. Formatea \
los montos de forma legible (ej. ₡12.4M en lugar de 12400000)."""


class SngAiDashboard(models.AbstractModel):
    _name = 'sng.ai.dashboard'
    _description = 'Dashboard IA - servicios de datos'

    # ------------------------------------------------------------------
    # Recolección de datos (SQL agregado, filtrado por compañías activas)
    # ------------------------------------------------------------------

    VALID_PERIODS = (1, 3, 6, 12)

    def _company_ids(self):
        return tuple(self.env.companies.ids)

    def _clean_months(self, months):
        return months if months in self.VALID_PERIODS else 3

    @api.model
    def get_dashboard_data(self, months=3):
        """Datos para el dashboard OWL. `months`: ventana de análisis (1/3/6/12)."""
        months = self._clean_months(months)
        company = self.env.company
        return {
            'months': months,
            'currency': {
                'symbol': company.currency_id.symbol,
                'name': company.currency_id.name,
            },
            'sales': self._get_sales_data(months),
            'collections': self._get_collections_data(months),
            'receivables': self._get_receivables_data(),
            'cxc': self._get_cxc_management_data(months),
            'inventory': self._get_inventory_data(),
            'inventory_wh': self._get_wh_inventory_data(months),
            'ai': self._get_ai_panel_data(),
        }

    def _period_start(self, months):
        """Primer día del mes, (months-1) meses atrás (incluye el mes actual)."""
        today = fields.Date.context_today(self)
        return today.replace(day=1) - relativedelta(months=months - 1)

    def _month_range(self, months):
        first_month = self._period_start(months)
        return [
            (first_month + relativedelta(months=i)).strftime('%Y-%m')
            for i in range(months)
        ]

    def _get_sales_data(self, months=3):
        cids = self._company_ids()
        today = fields.Date.context_today(self)
        first_month = self._period_start(months)

        # Ventas mensuales del período (facturas - notas de crédito, sin impuestos)
        self.env.cr.execute("""
            SELECT to_char(date_trunc('month', am.invoice_date), 'YYYY-MM') AS month,
                   COALESCE(SUM(am.amount_untaxed_signed), 0) AS total
            FROM account_move am
            WHERE am.move_type IN ('out_invoice', 'out_refund')
              AND am.state = 'posted'
              AND am.company_id IN %s
              AND am.invoice_date >= %s
            GROUP BY 1
            ORDER BY 1
        """, (cids, first_month))
        totals_by_month = {r[0]: float(r[1]) for r in self.env.cr.fetchall()}
        monthly = [
            {'month': m, 'total': totals_by_month.get(m, 0.0)}
            for m in self._month_range(months)
        ]

        first_of_month = today.replace(day=1)
        first_last_month = first_of_month - relativedelta(months=1)
        same_day_last_month = today - relativedelta(months=1)
        first_month_last_year = first_of_month - relativedelta(years=1)
        same_day_last_year = today - relativedelta(years=1)

        def _sum_sales(date_from, date_to):
            self.env.cr.execute("""
                SELECT COALESCE(SUM(am.amount_untaxed_signed), 0)
                FROM account_move am
                WHERE am.move_type IN ('out_invoice', 'out_refund')
                  AND am.state = 'posted'
                  AND am.company_id IN %s
                  AND am.invoice_date >= %s AND am.invoice_date <= %s
            """, (cids, date_from, date_to))
            return float(self.env.cr.fetchone()[0])

        current = _sum_sales(first_of_month, today)
        # Comparaciones al mismo día del mes para que sean justas
        prev_month = _sum_sales(first_last_month, same_day_last_month)
        last_year = _sum_sales(first_month_last_year, same_day_last_year)

        # Top vendedores asignados en el período seleccionado
        self.env.cr.execute("""
            SELECT COALESCE(rp.name, 'Sin vendedor asignado') AS salesperson,
                   COALESCE(SUM(am.amount_untaxed_signed), 0) AS total
            FROM account_move am
            LEFT JOIN res_partner rp ON rp.id = am.assigned_salesperson_id
            WHERE am.move_type IN ('out_invoice', 'out_refund')
              AND am.state = 'posted'
              AND am.company_id IN %s
              AND am.invoice_date >= %s
            GROUP BY 1
            ORDER BY 2 DESC
            LIMIT 10
        """, (cids, first_month))
        by_salesperson = [
            {'name': r[0], 'total': float(r[1])} for r in self.env.cr.fetchall()
        ]

        return {
            'monthly': monthly,
            'current_month': current,
            'previous_month_same_day': prev_month,
            'same_month_last_year_same_day': last_year,
            'by_salesperson': by_salesperson,
        }

    def _get_collections_data(self, months=3):
        """Cobranza: pagos de clientes aplicados a cuentas por cobrar."""
        cids = self._company_ids()
        today = fields.Date.context_today(self)
        first_month = self._period_start(months)

        self.env.cr.execute("""
            SELECT to_char(date_trunc('month', am.date), 'YYYY-MM') AS month,
                   COALESCE(SUM(aml.credit - aml.debit), 0) AS collected
            FROM account_payment ap
            JOIN account_move am ON am.id = ap.move_id
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE ap.payment_type = 'inbound'
              AND ap.partner_type = 'customer'
              AND am.state = 'posted'
              AND aa.account_type = 'asset_receivable'
              AND am.company_id IN %s
              AND am.date >= %s
            GROUP BY 1
        """, (cids, first_month))
        by_month = {r[0]: float(r[1]) for r in self.env.cr.fetchall()}
        monthly = [
            {'month': m, 'total': by_month.get(m, 0.0)}
            for m in self._month_range(months)
        ]
        current_month = by_month.get(today.strftime('%Y-%m'), 0.0)
        period_collected = sum(m['total'] for m in monthly)
        return {
            'monthly': monthly,
            'current_month': current_month,
            'period_collected': period_collected,
            'dso_days': self._get_dso(),
        }

    def _get_dso(self):
        """DSO estimado: CxC total / venta promedio diaria.

        La venta diaria se calcula sobre los últimos 3 meses COMPLETOS
        (alineado a meses): existen facturas erróneas y sus reversiones que se
        cancelan dentro del mismo mes; una ventana cortada a mitad de mes
        partiría esas parejas y distorsionaría el neto.
        """
        cids = self._company_ids()
        today = fields.Date.context_today(self)
        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.amount_residual), 0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND aml.company_id IN %s
        """, (cids,))
        ar_total = float(self.env.cr.fetchone()[0])

        period_end = today.replace(day=1)              # 1° del mes actual (excl.)
        period_start = period_end - relativedelta(months=3)
        days = (period_end - period_start).days
        self.env.cr.execute("""
            SELECT COALESCE(SUM(am.amount_total_signed), 0)
            FROM account_move am
            WHERE am.move_type IN ('out_invoice', 'out_refund')
              AND am.state = 'posted'
              AND am.company_id IN %s
              AND am.invoice_date >= %s AND am.invoice_date < %s
        """, (cids, period_start, period_end))
        net_sales = float(self.env.cr.fetchone()[0])
        if net_sales <= 0 or not days:
            return 0.0
        return round(ar_total / (net_sales / days), 1)

    def _partner_display_sql(self):
        """Usa el nombre comercial si el campo existe en esta BD."""
        if 'commercial_name' in self.env['res.partner']._fields:
            return "COALESCE(NULLIF(rp.commercial_name, ''), rp.name)"
        return "rp.name"

    def _get_receivables_data(self):
        cids = self._company_ids()
        today = fields.Date.context_today(self)

        # Saldos abiertos de cuentas por cobrar por antigüedad de vencimiento
        self.env.cr.execute("""
            SELECT
              COALESCE(SUM(aml.amount_residual), 0) AS total,
              COALESCE(SUM(CASE WHEN (%s::date - COALESCE(aml.date_maturity, aml.date)) <= 0
                                THEN aml.amount_residual ELSE 0 END), 0) AS not_due,
              COALESCE(SUM(CASE WHEN (%s::date - COALESCE(aml.date_maturity, aml.date)) BETWEEN 1 AND 30
                                THEN aml.amount_residual ELSE 0 END), 0) AS d1_30,
              COALESCE(SUM(CASE WHEN (%s::date - COALESCE(aml.date_maturity, aml.date)) BETWEEN 31 AND 60
                                THEN aml.amount_residual ELSE 0 END), 0) AS d31_60,
              COALESCE(SUM(CASE WHEN (%s::date - COALESCE(aml.date_maturity, aml.date)) BETWEEN 61 AND 90
                                THEN aml.amount_residual ELSE 0 END), 0) AS d61_90,
              COALESCE(SUM(CASE WHEN (%s::date - COALESCE(aml.date_maturity, aml.date)) > 90
                                THEN aml.amount_residual ELSE 0 END), 0) AS d90_plus
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND aml.company_id IN %s
        """, (today, today, today, today, today, cids))
        row = self.env.cr.fetchone()
        buckets = {
            'total': float(row[0]),
            'not_due': float(row[1]),
            'd1_30': float(row[2]),
            'd31_60': float(row[3]),
            'd61_90': float(row[4]),
            'd90_plus': float(row[5]),
        }
        buckets['overdue'] = buckets['total'] - buckets['not_due']

        # Top clientes con saldo vencido
        partner_name = self._partner_display_sql()
        self.env.cr.execute("""
            SELECT {partner_name} AS partner,
                   COALESCE(SUM(aml.amount_residual), 0) AS overdue,
                   MAX(%s::date - COALESCE(aml.date_maturity, aml.date)) AS max_days
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            JOIN res_partner rp ON rp.id = aml.partner_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND aml.company_id IN %s
              AND COALESCE(aml.date_maturity, aml.date) < %s
            GROUP BY 1
            HAVING SUM(aml.amount_residual) > 0
            ORDER BY 2 DESC
            LIMIT 10
        """.format(partner_name=partner_name), (today, cids, today))
        top_debtors = [
            {'name': r[0], 'overdue': float(r[1]), 'max_days': int(r[2] or 0)}
            for r in self.env.cr.fetchall()
        ]

        return {'buckets': buckets, 'top_debtors': top_debtors}

    # ------------------------------------------------------------------
    # Gestión de cobranza (pestaña Cuentas por cobrar)
    # ------------------------------------------------------------------

    def _get_cxc_management_data(self, months=3):
        """Datos para gestionar el cobro y mejorar la liquidez.

        - `call_list`: clientes a gestionar hoy, priorizados por monto vencido
          ponderado por antigüedad, con contacto y fecha del último pago.
        - `monthly`: facturado (con IVA) vs cobrado por mes y tasa de
          recuperación. Con IVA porque los pagos incluyen el impuesto.
        - `top_overdue_invoices`: facturas vencidas más grandes.
        """
        cids = self._company_ids()
        today = fields.Date.context_today(self)
        first_month = self._period_start(months)
        partner_name = self._partner_display_sql()
        partner_fields = self.env['res.partner']._fields
        phone_sql = ("COALESCE(NULLIF(rp.mobile, ''), rp.phone)"
                     if 'mobile' in partner_fields else "rp.phone")

        # Lista de cobro: saldos abiertos por cliente con al menos algo vencido
        self.env.cr.execute("""
            SELECT rp.id,
                   {partner_name} AS partner,
                   {phone_sql} AS phone,
                   rp.email,
                   COALESCE(SUM(aml.amount_residual), 0) AS total_open,
                   COALESCE(SUM(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s
                                     THEN aml.amount_residual ELSE 0 END), 0) AS overdue,
                   COUNT(*) FILTER (
                       WHERE COALESCE(aml.date_maturity, aml.date) < %s
                         AND aml.amount_residual > 0) AS overdue_count,
                   COALESCE(MAX(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s
                            THEN %s::date - COALESCE(aml.date_maturity, aml.date) END), 0) AS max_days,
                   COALESCE(
                       SUM(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s
                                THEN aml.amount_residual
                                     * (%s::date - COALESCE(aml.date_maturity, aml.date))
                                ELSE 0 END)
                       / NULLIF(SUM(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s
                                         THEN aml.amount_residual ELSE 0 END), 0),
                       0) AS weighted_days
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            JOIN res_partner rp ON rp.id = aml.partner_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND aml.company_id IN %s
            GROUP BY rp.id
            HAVING SUM(CASE WHEN COALESCE(aml.date_maturity, aml.date) < %s
                            THEN aml.amount_residual ELSE 0 END) > 0
        """.format(partner_name=partner_name, phone_sql=phone_sql),
            (today, today, today, today, today, today, today, cids, today))
        rows = self.env.cr.fetchall()

        # Último pago recibido por cliente
        partner_ids = tuple(r[0] for r in rows) or (0,)
        self.env.cr.execute("""
            SELECT ap.partner_id, MAX(am.date)
            FROM account_payment ap
            JOIN account_move am ON am.id = ap.move_id
            WHERE ap.payment_type = 'inbound'
              AND ap.partner_type = 'customer'
              AND am.state = 'posted'
              AND am.company_id IN %s
              AND ap.partner_id IN %s
            GROUP BY 1
        """, (cids, partner_ids))
        last_payment = dict(self.env.cr.fetchall())

        call_list = []
        for pid, name, phone, email, total_open, overdue, count, max_days, w_days in rows:
            overdue = float(overdue)
            w_days = float(w_days or 0)
            max_days = int(max_days or 0)
            paid_on = last_payment.get(pid)
            call_list.append({
                'partner_id': pid,
                'name': name,
                'phone': phone or '',
                'email': email or '',
                'total_open': float(total_open),
                'overdue': overdue,
                'overdue_count': int(count or 0),
                'max_days': max_days,
                'weighted_days': round(w_days),
                'last_payment': fields.Date.to_string(paid_on) if paid_on else None,
                # Prioridad: monto vencido ponderado por antigüedad promedio
                'score': overdue * (1 + min(w_days, 180) / 90.0),
            })
        call_list.sort(key=lambda c: -c['score'])
        call_list = call_list[:15]

        # Facturado (con IVA) vs cobrado por mes; a nivel de mes completo las
        # facturas erróneas de moneda y sus reversiones se cancelan entre sí.
        self.env.cr.execute("""
            SELECT to_char(date_trunc('month', am.invoice_date), 'YYYY-MM') AS month,
                   COALESCE(SUM(am.amount_total_signed), 0) AS total
            FROM account_move am
            WHERE am.move_type IN ('out_invoice', 'out_refund')
              AND am.state = 'posted'
              AND am.company_id IN %s
              AND am.invoice_date >= %s
            GROUP BY 1
        """, (cids, first_month))
        invoiced_by_month = {r[0]: float(r[1]) for r in self.env.cr.fetchall()}
        collections = self._get_collections_data(months)
        collected_by_month = {m['month']: m['total'] for m in collections['monthly']}
        monthly = []
        for m in self._month_range(months):
            invoiced = invoiced_by_month.get(m, 0.0)
            collected = collected_by_month.get(m, 0.0)
            monthly.append({
                'month': m,
                'invoiced': invoiced,
                'collected': collected,
                'rate': round(collected / invoiced * 100, 1) if invoiced > 0 else None,
            })
        period_invoiced = sum(m['invoiced'] for m in monthly)
        period_collected = sum(m['collected'] for m in monthly)

        # Facturas vencidas más grandes
        self.env.cr.execute("""
            SELECT am.name,
                   {partner_name} AS partner,
                   MIN(COALESCE(aml.date_maturity, aml.date)) AS due_date,
                   MAX(%s::date - COALESCE(aml.date_maturity, aml.date)) AS days,
                   SUM(aml.amount_residual) AS residual
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            JOIN res_partner rp ON rp.id = aml.partner_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND aml.company_id IN %s
              AND COALESCE(aml.date_maturity, aml.date) < %s
            GROUP BY am.id, rp.id
            HAVING SUM(aml.amount_residual) > 0
            ORDER BY 5 DESC
            LIMIT 10
        """.format(partner_name=partner_name), (today, cids, today))
        top_overdue_invoices = [
            {
                'invoice': r[0],
                'partner': r[1],
                'due_date': fields.Date.to_string(r[2]),
                'days': int(r[3] or 0),
                'residual': float(r[4]),
            }
            for r in self.env.cr.fetchall()
        ]

        return {
            'call_list': call_list,
            'monthly': monthly,
            'period_invoiced': period_invoiced,
            'period_collected': period_collected,
            'collection_rate': round(period_collected / period_invoiced * 100, 1)
                if period_invoiced > 0 else None,
            'top_overdue_invoices': top_overdue_invoices,
        }

    def _get_inventory_data(self):
        if 'stock.valuation.layer' not in self.env:
            return {'total': 0.0, 'by_category': [], 'available': False}
        cids = self._company_ids()
        self.env.cr.execute("""
            SELECT COALESCE(pc.complete_name, 'Sin categoría') AS category,
                   COALESCE(SUM(svl.value), 0) AS value
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN product_category pc ON pc.id = pt.categ_id
            WHERE svl.company_id IN %s
            GROUP BY 1
            HAVING SUM(svl.value) != 0
            ORDER BY 2 DESC
        """, (cids,))
        rows = [{'category': r[0], 'value': float(r[1])} for r in self.env.cr.fetchall()]
        total = sum(r['value'] for r in rows)
        return {'total': total, 'by_category': rows[:10], 'available': True}

    # ------------------------------------------------------------------
    # Inventario del almacén principal (pestaña Inventario)
    # ------------------------------------------------------------------

    def _get_inventory_warehouses(self):
        """Almacenes de la pestaña de inventario (config, default: WH Regalarte)."""
        codes = (self.env['ir.config_parameter'].sudo().get_param(
            'sng_ai_dashboard.inventory_warehouse_codes') or 'WH')
        code_list = [c.strip() for c in codes.split(',') if c.strip()]
        return self.env['stock.warehouse'].search([
            ('code', 'in', code_list),
            ('company_id', 'in', self.env.companies.ids),
        ])

    def _get_operations_start_date(self):
        """Misma fecha de inicio de operaciones que usa sng_analisis_compras."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            'sng_analisis_compras.operations_start_date', '2026-04-01')
        try:
            value = fields.Date.from_string(param)
        except ValueError:
            value = None
        return value or fields.Date.from_string('2026-04-01')

    def _get_wh_inventory_data(self, months=3):
        """Métricas de inventario del almacén principal.

        Misma lógica que sng_analisis_compras: promedio mensual = venta neta
        facturada ÷ (días del rango ÷ 30), recortando el inicio del rango a la
        fecha de inicio de operaciones; ventas de TODOS los almacenes; stock
        solo de las ubicaciones internas del almacén configurado.
        """
        warehouses = self._get_inventory_warehouses()
        if not warehouses:
            return {'available': False}
        cids = self._company_ids()
        today = fields.Date.context_today(self)

        # Ventana de promedio (recortada a inicio de operaciones)
        date_from = max(self._period_start(months), self._get_operations_start_date())
        avg_months = max(((today - date_from).days + 1), 1) / 30.0

        # Stock por producto en ubicaciones internas del almacén
        lot_stock_ids = warehouses.mapped('lot_stock_id').ids
        location_ids = tuple(self.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('id', 'child_of', lot_stock_ids),
        ]).ids)
        if not location_ids:
            return {'available': False}
        self.env.cr.execute("""
            SELECT sq.product_id, SUM(sq.quantity) AS qty
            FROM stock_quant sq
            WHERE sq.location_id IN %s
              AND sq.company_id IN %s
            GROUP BY 1
            HAVING SUM(sq.quantity) != 0
        """, (location_ids, cids))
        stock_by_product = {r[0]: float(r[1]) for r in self.env.cr.fetchall()}

        # Ventas netas por producto en unidades y monto (todas las bodegas,
        # como el default de sng_analisis_compras). El monto sale de aml.balance
        # (moneda de la compañía): crédito en facturas, débito en NC.
        self.env.cr.execute("""
            SELECT aml.product_id,
                   SUM(CASE WHEN am.move_type = 'out_invoice'
                            THEN aml.quantity ELSE -aml.quantity END) AS qty,
                   -SUM(aml.balance) AS revenue
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.move_type IN ('out_invoice', 'out_refund')
              AND am.state = 'posted'
              AND am.company_id IN %s
              AND am.invoice_date >= %s
              AND aml.display_type = 'product'
              AND aml.product_id IS NOT NULL
            GROUP BY 1
        """, (cids, date_from))
        rows = self.env.cr.fetchall()
        sales_by_product = {r[0]: float(r[1]) for r in rows}
        revenue_by_product = {r[0]: float(r[2]) for r in rows}

        # Costo y categoría vía ORM (standard_price es multi-compañía)
        product_ids = list(set(stock_by_product) | set(sales_by_product))
        products = self.env['product.product'].sudo().browse(product_ids)
        categories = {}
        no_movement = []
        sellers = []
        total_value = total_qty = total_sales_qty = 0.0
        for product in products:
            qty = stock_by_product.get(product.id, 0.0)
            sold = sales_by_product.get(product.id, 0.0)
            revenue = revenue_by_product.get(product.id, 0.0)
            cost = product.standard_price or 0.0
            value = qty * cost
            display_name = ("[%s] %s" % (product.default_code, product.name)) \
                if product.default_code else product.name
            categ = product.categ_id.complete_name or 'Sin categoría'
            cat = categories.setdefault(
                categ, {'category': categ, 'qty': 0.0, 'value': 0.0, 'sold': 0.0})
            cat['qty'] += qty
            cat['value'] += value
            cat['sold'] += max(sold, 0.0)
            total_qty += qty
            total_value += value
            total_sales_qty += max(sold, 0.0)
            if qty > 0 and sold <= 0:
                no_movement.append({
                    'name': display_name,
                    'qty': qty,
                    'value': value,
                })
            if sold > 0:
                monthly_avg = sold / avg_months if avg_months else 0.0
                margin_pct = None
                if revenue > 0:
                    margin_pct = round((revenue - sold * cost) / revenue * 100, 1)
                sellers.append({
                    'name': display_name,
                    'qty_sold': round(sold, 1),
                    'revenue': revenue,
                    'margin_pct': margin_pct,
                    'monthly_avg': round(monthly_avg, 1),
                    'stock': qty,
                    'months_cover': round(qty / monthly_avg, 1) if monthly_avg > 0 else None,
                })

        for cat in categories.values():
            avg = cat['sold'] / avg_months if avg_months else 0.0
            cat['monthly_avg'] = round(avg, 1)
            cat['months_cover'] = round(cat['qty'] / avg, 1) if avg > 0 else None

        total_avg = total_sales_qty / avg_months if avg_months else 0.0
        no_movement.sort(key=lambda item: -item['value'])
        by_category = sorted(categories.values(), key=lambda c: -c['value'])
        # Más vendidos por monto facturado
        top_sellers = sorted(sellers, key=lambda s: -s['revenue'])[:10]
        # Riesgo de faltante: se venden bien y tienen menos de 1 mes de stock
        stockout_risk = sorted(
            [s for s in sellers
             if s['months_cover'] is not None and s['months_cover'] < 1.0],
            key=lambda s: -s['revenue'])[:10]
        return {
            'available': True,
            'warehouses': ", ".join(warehouses.mapped('name')),
            'avg_months_window': round(avg_months, 1),
            'total_value': total_value,
            'total_qty': total_qty,
            'months_cover': round(total_qty / total_avg, 1) if total_avg > 0 else None,
            'by_category': by_category[:12],
            'top_sellers': top_sellers,
            'stockout_risk': stockout_risk,
            'no_movement_count': len(no_movement),
            'no_movement_value': sum(i['value'] for i in no_movement),
            'no_movement_top': no_movement[:10],
        }

    def _get_ai_panel_data(self):
        """Último análisis + gasto IA del mes."""
        Analysis = self.env['sng.ai.dashboard.analysis']
        latest = Analysis.search(
            [('company_id', 'in', self.env.companies.ids)], limit=1)
        first_of_month = fields.Date.context_today(self).replace(day=1)
        spend = Analysis.read_group(
            [('create_date', '>=', fields.Datetime.to_string(first_of_month))],
            ['cost_usd:sum'], [])
        icp = self.env['ir.config_parameter'].sudo()
        provider = icp.get_param('sng_ai_dashboard.provider') or 'deepseek'
        api_key_param = ('sng_ai_dashboard.api_key'
                         if provider == 'anthropic'
                         else 'sng_ai_dashboard.deepseek_api_key')
        return {
            'latest': latest and {
                'id': latest.id,
                'name': latest.name,
                'content': latest.content or '',
                'model_used': latest.model_used or '',
                'cost_usd': latest.cost_usd,
                'period_months': latest.period_months,
            } or False,
            'month_spend_usd': (spend and spend[0].get('cost_usd') or 0.0),
            'configured': bool(icp.get_param(api_key_param)),
        }

    # ------------------------------------------------------------------
    # Generación del análisis con el proveedor configurado
    # ------------------------------------------------------------------

    def _collect_payload(self, months=3):
        today = fields.Date.context_today(self)
        cxc = self._get_cxc_management_data(months)
        # Sin datos de contacto: la IA no necesita teléfonos ni correos
        cxc = dict(cxc, call_list=[
            {k: v for k, v in c.items()
             if k not in ('phone', 'email', 'partner_id', 'score')}
            for c in cxc['call_list']
        ])
        return {
            'fecha_corte': fields.Date.to_string(today),
            'periodo_meses': months,
            'moneda': self.env.company.currency_id.name,
            'ventas': self._get_sales_data(months),
            'cobranza': self._get_collections_data(months),
            'cuentas_por_cobrar': self._get_receivables_data(),
            'gestion_cobranza': cxc,
            'inventario_valoracion_global': self._get_inventory_data(),
            'inventario_almacen_principal': self._get_wh_inventory_data(months),
        }

    def _get_ai_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        provider = icp.get_param('sng_ai_dashboard.provider') or 'deepseek'
        if provider != 'anthropic':
            return {
                'provider': 'deepseek',
                'api_key': icp.get_param('sng_ai_dashboard.deepseek_api_key'),
                'model': (icp.get_param('sng_ai_dashboard.deepseek_model')
                          or 'deepseek-v4-flash'),
                'base_url': (icp.get_param('sng_ai_dashboard.deepseek_base_url')
                             or 'https://api.deepseek.com').rstrip('/'),
            }
        return {
            'provider': 'anthropic',
            'api_key': icp.get_param('sng_ai_dashboard.api_key'),
            'model': icp.get_param('sng_ai_dashboard.model') or 'claude-opus-4-8',
        }

    def _generate_with_anthropic(self, config, user_message):
        try:
            import anthropic
        except ImportError:
            raise UserError(_(
                "El paquete Python 'anthropic' no está instalado en el servidor. "
                "Ejecute: pip install anthropic"))

        client = anthropic.Anthropic(
            api_key=config['api_key'], timeout=300.0, max_retries=2)
        params = {
            'model': config['model'],
            'max_tokens': 8000,
            'system': SYSTEM_PROMPT,
            'messages': [{'role': 'user', 'content': user_message}],
        }
        if not config['model'].startswith('claude-haiku'):
            params['thinking'] = {'type': 'adaptive'}
        try:
            response = client.messages.create(**params)
        except anthropic.AuthenticationError:
            raise UserError(_("API key de Anthropic inválida o revocada."))
        except anthropic.RateLimitError:
            raise UserError(_(
                "Límite de peticiones alcanzado en la API de Anthropic. "
                "Intente de nuevo en unos minutos."))
        except anthropic.APIConnectionError:
            raise UserError(_(
                "No se pudo conectar con la API de Anthropic. "
                "Revise la conexión a internet del servidor."))
        except anthropic.APIStatusError as error:
            raise UserError(_("Error de la API de Anthropic (%s): %s")
                            % (error.status_code, error.message))

        if response.stop_reason == 'refusal':
            raise UserError(_("El modelo declinó generar el análisis. Intente de nuevo."))
        text = "".join(
            block.text for block in response.content if block.type == 'text')
        return {
            'content': text,
            'model': response.model,
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
        }

    def _generate_with_deepseek(self, config, user_message):
        try:
            response = requests.post(
                '%s/chat/completions' % config['base_url'],
                headers={
                    'Authorization': 'Bearer %s' % config['api_key'],
                    'Content-Type': 'application/json',
                },
                json={
                    'model': config['model'],
                    'max_tokens': 8000,
                    # El modo de razonamiento es el predeterminado en DeepSeek V4
                    # y puede consumir todos los tokens sin producir respuesta final.
                    'thinking': {'type': 'disabled'},
                    'messages': [
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_message},
                    ],
                },
                timeout=300,
            )
        except requests.exceptions.RequestException as error:
            raise UserError(_(
                "No se pudo conectar con la API de DeepSeek: %s") % error)

        if response.status_code == 401:
            raise UserError(_("API key de DeepSeek inválida o revocada."))
        if response.status_code == 429:
            raise UserError(_(
                "Límite de peticiones alcanzado en la API de DeepSeek. "
                "Intente de nuevo en unos minutos."))
        if not response.ok:
            try:
                detail = response.json().get('error', {}).get('message')
            except (ValueError, AttributeError):
                detail = response.text[:500]
            raise UserError(_("Error de la API de DeepSeek (%s): %s")
                            % (response.status_code, detail or response.reason))
        try:
            data = response.json()
            content = data['choices'][0]['message']['content']
            usage = data.get('usage') or {}
        except (ValueError, KeyError, IndexError, TypeError):
            raise UserError(_("DeepSeek devolvió una respuesta con formato inválido."))
        return {
            'content': content or '',
            'model': data.get('model') or config['model'],
            'input_tokens': usage.get('prompt_tokens') or 0,
            'output_tokens': usage.get('completion_tokens') or 0,
        }

    @api.model
    def action_generate_analysis(self, origin='manual', months=3):
        months = self._clean_months(months)
        config = self._get_ai_config()
        if not config['api_key']:
            raise UserError(_(
                "No hay API key configurada. Vaya a Ajustes > Dashboard IA y "
                "configure la clave del proveedor seleccionado."))

        payload = self._collect_payload(months)
        user_message = (
            "Indicadores del negocio al %s (período de análisis: %s meses):\n\n"
            "```json\n%s\n```"
            % (payload['fecha_corte'], months,
               json.dumps(payload, ensure_ascii=False, default=str))
        )

        generator = (self._generate_with_deepseek
                     if config['provider'] == 'deepseek'
                     else self._generate_with_anthropic)
        result = generator(config, user_message)
        text = result['content']
        if not text.strip():
            raise UserError(_("La API devolvió una respuesta vacía. Intente de nuevo."))

        p_in, p_out = PRICING.get(result['model'], (0.0, 0.0))
        cost = ((result['input_tokens'] / 1e6 * p_in)
                + (result['output_tokens'] / 1e6 * p_out))

        self.env['sng.ai.dashboard.analysis'].create({
            'content': text,
            'provider_used': config['provider'],
            'model_used': result['model'],
            'input_tokens': result['input_tokens'],
            'output_tokens': result['output_tokens'],
            'cost_usd': cost,
            'origin': origin,
            'period_months': months,
        })
        _logger.info(
            "Análisis IA generado con %s (%s): %s tokens entrada, %s salida, $%.4f",
            config['provider'], result['model'], result['input_tokens'],
            result['output_tokens'], cost)
        return self._get_ai_panel_data()

    @api.model
    def cron_generate_analysis(self):
        """Cron diario: genera análisis solo si hay API key configurada."""
        if not self._get_ai_config()['api_key']:
            _logger.info("Dashboard IA: cron omitido, sin API key configurada.")
            return
        try:
            self.action_generate_analysis(origin='cron', months=3)
        except Exception:
            _logger.exception("Dashboard IA: error generando el análisis programado.")
