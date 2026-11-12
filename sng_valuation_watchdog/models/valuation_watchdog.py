# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# Parámetros de sistema (Ajustes > Técnico > Parámetros del sistema)
PARAM_EMAILS = "sng_valuation_watchdog.email_to"
PARAM_COST_PRICE_RATIO = "sng_valuation_watchdog.cost_price_ratio"  # costo/precio sospechoso
PARAM_MAX_ROWS = "sng_valuation_watchdog.max_rows"

# Orden de las secciones en el correo y en la pantalla
CHECK_ORDER = ["descuadre", "entrada_precio_venta", "margen", "costo_cero", "svl_negativa"]


class ValuationWatchdog(models.AbstractModel):
    _name = "sng.valuation.watchdog"
    _description = "Vigilante de valoración de inventario"

    # ------------------------------------------------------------------
    # Chequeos: cada uno devuelve una lista de dicts con product_id, code,
    # name y los valores propios del chequeo (ver _section_meta).
    # ------------------------------------------------------------------

    def _check_descuadre_quants_svl(self, company):
        """Stock físico vs cantidad valorada (SVL). Origen del caso 113003040."""
        self.env.cr.execute(
            """
            WITH svl AS (
                SELECT product_id, SUM(quantity) q
                  FROM stock_valuation_layer WHERE company_id=%s GROUP BY product_id),
                 qt AS (
                SELECT q.product_id, SUM(q.quantity) q
                  FROM stock_quant q JOIN stock_location l ON l.id=q.location_id
                 WHERE l.usage='internal' OR (l.usage='transit' AND l.company_id IS NOT NULL)
                 GROUP BY q.product_id)
            SELECT pp.id, pp.default_code, pt.name->>'es_CR', pt.name->>'en_US',
                   COALESCE(qt.q,0), COALESCE(svl.q,0),
                   COALESCE(qt.q,0)-COALESCE(svl.q,0)
              FROM product_product pp
              JOIN product_template pt ON pt.id=pp.product_tmpl_id
              LEFT JOIN svl ON svl.product_id=pp.id
              LEFT JOIN qt ON qt.product_id=pp.id
             WHERE pt.type='consu' AND pt.is_storable AND pp.active
               AND ABS(COALESCE(qt.q,0)-COALESCE(svl.q,0)) > 0.01
             ORDER BY ABS(COALESCE(qt.q,0)-COALESCE(svl.q,0)) DESC
            """,
            (company.id,),
        )
        return [
            {
                "product_id": pid, "code": code or "", "name": name_cr or name_en or "",
                "qty_fisica": q, "qty_valorada": s, "diferencia": d,
            }
            for pid, code, name_cr, name_en, q, s, d in self.env.cr.fetchall()
        ]

    def _check_entradas_a_precio_venta(self, company, ratio):
        """Entradas de las últimas 25 h sin compra de origen valoradas cerca del
        precio de venta (fuga tipo consignaciones)."""
        self.env.cr.execute(
            """
            SELECT pp.id, sm.id, sm.reference, pp.default_code, pt.name->>'es_CR', pt.name->>'en_US',
                   svl.quantity, svl.unit_cost, pt.list_price
              FROM stock_valuation_layer svl
              JOIN stock_move sm ON sm.id=svl.stock_move_id
              JOIN product_product pp ON pp.id=svl.product_id
              JOIN product_template pt ON pt.id=pp.product_tmpl_id
             WHERE svl.company_id=%s AND svl.quantity>0
               AND svl.create_date >= (now() at time zone 'UTC') - interval '25 hours'
               AND sm.purchase_line_id IS NULL AND sm.origin_returned_move_id IS NULL
               AND pt.list_price>0 AND svl.unit_cost >= pt.list_price*%s
             ORDER BY svl.value DESC
            """,
            (company.id, ratio),
        )
        return [
            {
                "product_id": pid, "move_id": mid, "reference": ref or "",
                "code": code or "", "name": name_cr or name_en or "",
                "qty_valorada": q, "costo": uc, "precio_venta": lp,
            }
            for pid, mid, ref, code, name_cr, name_en, q, uc, lp in self.env.cr.fetchall()
        ]

    def _check_costo_vs_precio(self, company, ratio):
        """Productos con stock cuyo costo estándar es sospechosamente alto
        respecto al precio de venta (margen anómalo, caso costo ₡100k)."""
        self.env.cr.execute(
            """
            WITH qt AS (
                SELECT q.product_id, SUM(q.quantity) q
                  FROM stock_quant q JOIN stock_location l ON l.id=q.location_id
                 WHERE l.usage='internal' GROUP BY q.product_id)
            SELECT pp.id, pp.default_code, pt.name->>'es_CR', pt.name->>'en_US',
                   qt.q, (pp.standard_price->>%s)::numeric, pt.list_price
              FROM product_product pp
              JOIN product_template pt ON pt.id=pp.product_tmpl_id
              JOIN qt ON qt.product_id=pp.id AND qt.q > 0
             WHERE pp.active AND pt.type='consu' AND pt.is_storable
               AND pt.list_price > 0
               AND (pp.standard_price->>%s)::numeric >= pt.list_price*%s
             ORDER BY (pp.standard_price->>%s)::numeric * qt.q DESC
            """,
            (str(company.id), str(company.id), ratio, str(company.id)),
        )
        return [
            {
                "product_id": pid, "code": code or "", "name": name_cr or name_en or "",
                "qty_fisica": q, "costo": std, "precio_venta": lp,
            }
            for pid, code, name_cr, name_en, q, std, lp in self.env.cr.fetchall()
        ]

    def _check_stock_sin_costo(self, company):
        """Productos con stock físico y costo estándar 0 (quedan fuera de la valoración)."""
        self.env.cr.execute(
            """
            WITH qt AS (
                SELECT q.product_id, SUM(q.quantity) q
                  FROM stock_quant q JOIN stock_location l ON l.id=q.location_id
                 WHERE l.usage='internal' GROUP BY q.product_id)
            SELECT pp.id, pp.default_code, pt.name->>'es_CR', pt.name->>'en_US', qt.q
              FROM product_product pp
              JOIN product_template pt ON pt.id=pp.product_tmpl_id
              JOIN qt ON qt.product_id=pp.id AND qt.q > 0
             WHERE pp.active AND pt.type='consu' AND pt.is_storable
               AND COALESCE((pp.standard_price->>%s)::numeric, 0) = 0
             ORDER BY qt.q DESC
            """,
            (str(company.id),),
        )
        return [
            {"product_id": pid, "code": code or "", "name": name_cr or name_en or "", "qty_fisica": q}
            for pid, code, name_cr, name_en, q in self.env.cr.fetchall()
        ]

    def _check_svl_negativa(self, company):
        """Productos cuya cantidad valorada total es negativa (inventario contable
        negativo: el próximo vacuum puede corromper el costo promedio)."""
        self.env.cr.execute(
            """
            SELECT pp.id, pp.default_code, pt.name->>'es_CR', pt.name->>'en_US',
                   SUM(svl.quantity), SUM(svl.value)
              FROM stock_valuation_layer svl
              JOIN product_product pp ON pp.id=svl.product_id
              JOIN product_template pt ON pt.id=pp.product_tmpl_id
             WHERE svl.company_id=%s AND pp.active AND pt.type='consu' AND pt.is_storable
             GROUP BY 1,2,3,4 HAVING SUM(svl.quantity) < -0.01
             ORDER BY SUM(svl.quantity)
            """,
            (company.id,),
        )
        return [
            {
                "product_id": pid, "code": code or "", "name": name_cr or name_en or "",
                "qty_valorada": q, "valor": v,
            }
            for pid, code, name_cr, name_en, q, v in self.env.cr.fetchall()
        ]

    # ------------------------------------------------------------------
    # Ejecución, presentación y persistencia
    # ------------------------------------------------------------------

    @api.model
    def _get_ratio(self):
        try:
            return float(self.env["ir.config_parameter"].sudo().get_param(PARAM_COST_PRICE_RATIO, "0.8"))
        except ValueError:
            return 0.8

    def _run_checks(self, company, ratio):
        """Devuelve {clave: [filas]} con todas las anomalías actuales."""
        self.env.flush_all()
        return {
            "descuadre": self._check_descuadre_quants_svl(company),
            "entrada_precio_venta": self._check_entradas_a_precio_venta(company, ratio),
            "margen": self._check_costo_vs_precio(company, ratio),
            "costo_cero": self._check_stock_sin_costo(company),
            "svl_negativa": self._check_svl_negativa(company),
        }

    def _section_meta(self, key, ratio):
        """(título, encabezados, función que convierte una fila en celdas) para el correo."""
        qty = "{:,.0f}".format
        money = "{:,.2f}".format
        meta = {
            "descuadre": (
                _("Existencias físicas ≠ cantidad valorada (descuadre quants vs SVL)"),
                [_("Código"), _("Producto"), _("Físico"), _("Valorado"), _("Diferencia")],
                lambda r: (r["code"], r["name"], qty(r["qty_fisica"]), qty(r["qty_valorada"]), qty(r["diferencia"])),
            ),
            "entrada_precio_venta": (
                _("Entradas valoradas cerca del precio de venta (últimas 25 h)"),
                [_("Referencia"), _("Código"), _("Producto"), _("Cant."), _("Costo capa"), _("Precio venta")],
                lambda r: (r["reference"], r["code"], r["name"], qty(r["qty_valorada"]),
                           money(r["costo"]), money(r["precio_venta"])),
            ),
            "margen": (
                _("Costo estándar ≥ %(pct)s%% del precio de venta (margen anómalo)", pct=int(ratio * 100)),
                [_("Código"), _("Producto"), _("Stock"), _("Costo"), _("Precio venta")],
                lambda r: (r["code"], r["name"], qty(r["qty_fisica"]), money(r["costo"]), money(r["precio_venta"])),
            ),
            "costo_cero": (
                _("Stock con costo estándar en 0"),
                [_("Código"), _("Producto"), _("Stock")],
                lambda r: (r["code"], r["name"], qty(r["qty_fisica"])),
            ),
            "svl_negativa": (
                _("Cantidad valorada negativa (inventario contable en negativo)"),
                [_("Código"), _("Producto"), _("Cant. valorada"), _("Valor")],
                lambda r: (r["code"], r["name"], qty(r["qty_valorada"]), money(r["valor"])),
            ),
        }
        return meta[key]

    @api.model
    def _refresh_anomalies(self, company=None, ratio=None):
        """Reconstruye sng.valuation.anomaly para la compañía: actualiza las líneas
        que siguen vigentes (conservando first_seen), crea las nuevas y borra las
        que ya no cumplen. Devuelve el resultado de _run_checks."""
        company = company or self.env.company
        ratio = self._get_ratio() if ratio is None else ratio
        results = self._run_checks(company, ratio)

        Anomaly = self.env["sng.valuation.anomaly"].sudo()
        existing = Anomaly.search([("company_id", "=", company.id)])
        by_key = {(a.anomaly_type, a.product_id.id, a.move_id.id or False): a for a in existing}
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        kept = Anomaly.browse()
        to_create = {}
        for key in CHECK_ORDER:
            for row in results[key]:
                # SQL devuelve Decimal en columnas numeric: normalizar a float
                num = {f: float(row.get(f) or 0.0) for f in (
                    "qty_fisica", "qty_valorada", "diferencia", "costo", "precio_venta", "valor")}
                vals = {
                    **num,
                    "margen_pct": (num["costo"] / num["precio_venta"] * 100.0) if num["precio_venta"] else 0.0,
                    "reference": row.get("reference") or False,
                    "last_refresh": now,
                }
                ident = (key, row["product_id"], row.get("move_id") or False)
                rec = by_key.get(ident)
                if rec:
                    rec.write(vals)
                    kept |= rec
                else:
                    vals.update(
                        anomaly_type=key,
                        product_id=row["product_id"],
                        move_id=row.get("move_id") or False,
                        company_id=company.id,
                        first_seen=today,
                    )
                    to_create[ident] = vals
        (existing - kept).unlink()
        if to_create:
            Anomaly.create(list(to_create.values()))
        return results

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------

    @api.model
    def cron_run_checks(self):
        icp = self.env["ir.config_parameter"].sudo()
        ratio = self._get_ratio()
        try:
            max_rows = int(icp.get_param(PARAM_MAX_ROWS, "25"))
        except ValueError:
            max_rows = 25

        company = self.env.company
        results = self._refresh_anomalies(company, ratio)

        email_to = (icp.get_param(PARAM_EMAILS) or "").strip()
        if not email_to:
            _logger.warning(
                "sng_valuation_watchdog: sin destinatarios (parámetro %s); no se envía correo.",
                PARAM_EMAILS,
            )
            return

        findings = []
        for key in CHECK_ORDER:
            if results[key]:
                title, headers, fmt = self._section_meta(key, ratio)
                findings.append((title, headers, [fmt(r) for r in results[key]]))
        if not findings:
            _logger.info("sng_valuation_watchdog: sin anomalías.")
            return

        today = fields.Date.context_today(self)
        parts = [
            "<div style='font-family:Arial,sans-serif;font-size:13px;color:#333'>",
            "<p>%s</p>"
            % _(
                "El vigilante de valoración de inventario detectó las siguientes "
                "anomalías en %(company)s:",
                company=company.name,
            ),
        ]
        for title, headers, rows in findings:
            parts.append(
                "<h3 style='margin:14px 0 4px'>%s <span style='color:#888'>(%s)</span></h3>"
                % (title, len(rows))
            )
            parts.append(
                "<table style='border-collapse:collapse;font-size:12px'><tr>%s</tr>"
                % "".join(
                    "<th style='border:1px solid #ccc;padding:2px 8px;background:#f2f2f2;text-align:left'>%s</th>" % h
                    for h in headers
                )
            )
            for row in rows[:max_rows]:
                parts.append(
                    "<tr>%s</tr>"
                    % "".join(
                        "<td style='border:1px solid #ccc;padding:2px 8px'>%s</td>" % c
                        for c in row
                    )
                )
            parts.append("</table>")
            if len(rows) > max_rows:
                parts.append(
                    "<p style='color:#888'>%s</p>"
                    % _("… y %(n)s más.", n=len(rows) - max_rows)
                )
        base_url = (icp.get_param("web.base.url") or "").rstrip("/")
        if base_url:
            parts.append(
                "<p style='margin-top:14px'><a href='%s/odoo/action-sng_valuation_watchdog.action_valuation_anomaly'>%s</a></p>"
                % (base_url, _("Ver la lista completa en Odoo (Inventario > Informes > Anomalías de valoración)"))
            )
        parts.append(
            "<p style='color:#888;font-size:11px'>%s</p></div>"
            % _(
                "Generado automáticamente por el módulo sng_valuation_watchdog. "
                "Umbral costo/precio: %(ratio)s. Destinatarios y umbrales se configuran "
                "en Parámetros del sistema (sng_valuation_watchdog.*).",
                ratio=ratio,
            )
        )

        self.env["mail.mail"].sudo().create(
            {
                "subject": _(
                    "[%(company)s] Alerta valoración de inventario %(date)s: %(n)s hallazgo(s)",
                    company=company.name,
                    date=today.strftime("%d/%m/%Y"),
                    n=sum(len(f[2]) for f in findings),
                ),
                "email_to": email_to,
                "email_from": company.email_formatted or self.env.user.email_formatted,
                "body_html": "".join(parts),
                "auto_delete": True,
            }
        )
        _logger.info(
            "sng_valuation_watchdog: correo enviado a %s con %s secciones.",
            email_to,
            len(findings),
        )
