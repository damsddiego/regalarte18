# -*- coding: utf-8 -*-
import io
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import json_default

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:  # pragma: no cover
    import xlsxwriter


LINE_TYPE_ROUTE = "route"
LINE_TYPE_SALESPERSON = "salesperson"

# Documentos de venta considerados: facturas y notas de crédito publicadas.
SALE_MOVE_TYPES = ("out_invoice", "out_refund")

# Base sobre la que se calcula el Peso %
WEIGHT_BASE_TOTAL = "total"      # Ventas Netas IVAI (impuestos incluidos)
WEIGHT_BASE_UNTAXED = "untaxed"  # Ventas Brutas A.I (sin impuestos)

# Secuencias reservadas para las filas "sin clasificar" (siempre al final).
UNASSIGNED_SEQUENCE = 999999


def _ensure_backing_table(cr, table_name):
    """Crea la tabla física del snapshot (el modelo es _auto=False)."""
    cr.execute(
        """
        SELECT c.relkind
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relname = %s
           AND n.nspname = 'public'
        """,
        (table_name,),
    )
    row = cr.fetchone()
    if row and row[0] == "v":
        cr.execute('DROP VIEW IF EXISTS "%s" CASCADE' % table_name)
    elif row and row[0] == "m":
        cr.execute('DROP MATERIALIZED VIEW IF EXISTS "%s" CASCADE' % table_name)
    cr.execute('CREATE TABLE IF NOT EXISTS "%s" (id SERIAL PRIMARY KEY)' % table_name)


class SngSalesRouteSalesReport(models.Model):
    _name = "sng.sales.route.sales.report"
    _description = "Ventas por Ruta y Vendedor"
    _auto = False
    _rec_name = "name"
    _order = "line_type, sequence, name"

    user_id = fields.Many2one("res.users", string="Usuario", readonly=True)
    date_from = fields.Date(string="Desde", readonly=True)
    date_to = fields.Date(string="Hasta", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)

    line_type = fields.Selection(
        [
            (LINE_TYPE_ROUTE, "Pesos por ruta"),
            (LINE_TYPE_SALESPERSON, "Pesos por vendedor"),
        ],
        string="Sección",
        readonly=True,
    )
    sequence = fields.Integer(string="Secuencia", readonly=True)
    code = fields.Char(string="Código", readonly=True)
    name = fields.Char(string="Nombre", readonly=True)
    sales_route_id = fields.Many2one("sng.sales.route", string="Ruta", readonly=True)
    salesperson_id = fields.Many2one("res.partner", string="Vendedor", readonly=True)
    route_salesperson_name = fields.Char(
        string="Vendedor de referencia",
        readonly=True,
        help="Vendedor de referencia de la ruta; si la ruta no lo tiene, el que más facturó en el periodo.",
    )
    amount_total = fields.Monetary(
        string="Ventas Netas IVAI",
        readonly=True,
        currency_field="currency_id",
        help="Suma del total con impuestos de facturas menos notas de crédito publicadas.",
    )
    amount_untaxed = fields.Monetary(
        string="Ventas Brutas A.I",
        readonly=True,
        currency_field="currency_id",
        help="Suma del importe sin impuestos de facturas menos notas de crédito publicadas.",
    )
    weight_base = fields.Selection(
        [
            (WEIGHT_BASE_TOTAL, "Ventas Netas IVAI"),
            (WEIGHT_BASE_UNTAXED, "Ventas Brutas A.I"),
        ],
        string="Base del peso",
        readonly=True,
    )
    weight = fields.Float(
        string="Peso %",
        readonly=True,
        digits=(16, 6),
        help="Participación de la fila sobre el total de la sección.",
    )
    invoice_count = fields.Integer(string="Documentos", readonly=True)

    _COLUMNS = {
        "user_id": "INTEGER NOT NULL",
        "date_from": "DATE",
        "date_to": "DATE",
        "company_id": "INTEGER",
        "currency_id": "INTEGER",
        "line_type": "VARCHAR",
        "sequence": "INTEGER",
        "code": "VARCHAR",
        "name": "VARCHAR",
        "sales_route_id": "INTEGER",
        "salesperson_id": "INTEGER",
        "route_salesperson_name": "VARCHAR",
        "amount_total": "NUMERIC",
        "amount_untaxed": "NUMERIC",
        "weight_base": "VARCHAR",
        "weight": "NUMERIC",
        "invoice_count": "INTEGER",
    }

    def init(self):
        _ensure_backing_table(self._cr, self._table)
        for col_name, col_type in self._COLUMNS.items():
            self._cr.execute(
                'ALTER TABLE "%s" ADD COLUMN IF NOT EXISTS "%s" %s'
                % (self._table, col_name, col_type)
            )
        self._cr.execute(
            """
            CREATE INDEX IF NOT EXISTS sng_sales_route_sales_report_user_idx
                ON sng_sales_route_sales_report (user_id);
            """
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_allowed_company_ids(self):
        return self.env.context.get("allowed_company_ids") or self.env.companies.ids

    @api.model
    def _get_snapshot_domain(self):
        return [("user_id", "=", self.env.user.id)]

    @api.model
    def _get_amounts(self, date_from, date_to, company_ids):
        """Devuelve (por_ruta, por_vendedor, por_ruta_vendedor, totales) del rango.

        Cada entrada trae el total con impuestos (``total``), el importe sin
        impuestos (``untaxed``) y la cantidad de documentos (``count``).

        El vendedor se toma de ``assigned_salesperson_id`` (vendedor asignado al
        cliente, módulo ``sng_invoice_assigned_salesperson``) y solo cuando está
        vacío se usa ``salesperson_id`` de la factura.
        """
        self._cr.execute(
            """
            SELECT am.sales_route_id AS route_id,
                   COALESCE(am.assigned_salesperson_id, am.salesperson_id) AS salesperson_id,
                   SUM(am.amount_total_signed) AS amount_total,
                   SUM(am.amount_untaxed_signed) AS amount_untaxed,
                   COUNT(*) AS doc_count
              FROM account_move am
             WHERE am.move_type IN %s
               AND am.state = 'posted'
               AND am.invoice_date >= %s
               AND am.invoice_date <= %s
               AND am.company_id IN %s
          GROUP BY am.sales_route_id,
                   COALESCE(am.assigned_salesperson_id, am.salesperson_id)
            """,
            (SALE_MOVE_TYPES, date_from, date_to, tuple(company_ids)),
        )
        by_route = {}
        by_salesperson = {}
        by_route_salesperson = {}
        totals = {"total": 0.0, "untaxed": 0.0, "count": 0}
        for row in self._cr.dictfetchall():
            values = {
                "total": float(row["amount_total"] or 0.0),
                "untaxed": float(row["amount_untaxed"] or 0.0),
                "count": row["doc_count"] or 0,
            }
            route_key = row["route_id"] or False
            salesperson_key = row["salesperson_id"] or False
            for store, key in ((by_route, route_key), (by_salesperson, salesperson_key)):
                bucket = store.setdefault(key, {"total": 0.0, "untaxed": 0.0, "count": 0})
                for field_name in ("total", "untaxed", "count"):
                    bucket[field_name] += values[field_name]
            route_map = by_route_salesperson.setdefault(route_key, {})
            route_map[salesperson_key] = route_map.get(salesperson_key, 0.0) + values["total"]
            for field_name in ("total", "untaxed", "count"):
                totals[field_name] += values[field_name]
        return by_route, by_salesperson, by_route_salesperson, totals

    @api.model
    def _get_route_salesperson_name(self, route, route_map):
        """Vendedor a mostrar en la fila de la ruta.

        Se usa el vendedor de referencia configurado en la ruta y, si no hay,
        el vendedor que más facturó en esa ruta durante el periodo.
        """
        if route.salesperson_id:
            return route.salesperson_id.name or ""
        candidates = {
            partner_id: amount
            for partner_id, amount in (route_map or {}).items()
            if partner_id
        }
        if not candidates:
            return ""
        best_id = max(candidates, key=lambda partner_id: candidates[partner_id])
        return self.env["res.partner"].browse(best_id).name or ""

    # ------------------------------------------------------------------
    # Auxiliar: documentos que originan cada monto
    # ------------------------------------------------------------------
    @api.model
    def _get_base_domain(self, date_from, date_to, company_ids=None):
        """Domino de los documentos considerados por el reporte."""
        return [
            ("move_type", "in", list(SALE_MOVE_TYPES)),
            ("state", "=", "posted"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
            ("company_id", "in", company_ids or self._get_allowed_company_ids()),
        ]

    def _get_line_domain(self):
        """Domino de los documentos que suman en esta línea del reporte."""
        self.ensure_one()
        domain = self._get_base_domain(self.date_from, self.date_to)
        if self.line_type == LINE_TYPE_ROUTE:
            return domain + [("sales_route_id", "=", self.sales_route_id.id or False)]
        # El vendedor efectivo es assigned_salesperson_id y, si está vacío,
        # salesperson_id: el dominio replica ese COALESCE.
        if self.salesperson_id:
            return domain + [
                "|",
                ("assigned_salesperson_id", "=", self.salesperson_id.id),
                "&",
                ("assigned_salesperson_id", "=", False),
                ("salesperson_id", "=", self.salesperson_id.id),
            ]
        return domain + [
            ("assigned_salesperson_id", "=", False),
            ("salesperson_id", "=", False),
        ]

    def action_view_moves(self):
        """Abre las facturas y notas de crédito que componen la línea."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos: %s") % (self.name or ""),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": self._get_line_domain(),
            "context": {"create": False},
        }

    def action_view_clients(self):
        """Abre el auxiliar por cliente filtrado por la línea."""
        self.ensure_one()
        client_model = self.env["sng.sales.route.client.report"]
        domain = client_model._get_snapshot_domain()
        if self.line_type == LINE_TYPE_ROUTE:
            domain += [("sales_route_id", "=", self.sales_route_id.id or False)]
        else:
            domain += [("salesperson_id", "=", self.salesperson_id.id or False)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Clientes: %s") % (self.name or ""),
            "res_model": client_model._name,
            "view_mode": "list",
            "domain": domain,
            "context": {"create": False, "edit": False, "delete": False},
        }

    # ------------------------------------------------------------------
    # Construcción del snapshot
    # ------------------------------------------------------------------
    @api.model
    def _rebuild_snapshot(
        self, date_from, date_to, include_zero=True, weight_base=WEIGHT_BASE_TOTAL
    ):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            raise UserError(_("Debe indicar la fecha inicial y la fecha final."))
        if date_from > date_to:
            raise UserError(_("La fecha inicial no puede ser posterior a la fecha final."))
        if weight_base not in (WEIGHT_BASE_TOTAL, WEIGHT_BASE_UNTAXED):
            weight_base = WEIGHT_BASE_TOTAL

        company_ids = self._get_allowed_company_ids()
        if not company_ids:
            raise UserError(_("No hay compañías activas para generar el reporte."))

        user = self.env.user
        company = self.env.company
        self._cr.execute(
            'DELETE FROM "%s" WHERE user_id = %%s' % self._table, (user.id,)
        )

        by_route, by_salesperson, by_route_salesperson, totals = self._get_amounts(
            date_from, date_to, company_ids
        )
        base_total = totals[weight_base]

        common = {
            "user_id": user.id,
            "date_from": date_from,
            "date_to": date_to,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "weight_base": weight_base,
        }
        empty = {"total": 0.0, "untaxed": 0.0, "count": 0}
        rows = []

        def _amount_values(values):
            """Montos y peso listos para insertar."""
            return {
                "amount_total": values["total"],
                "amount_untaxed": values["untaxed"],
                "invoice_count": values["count"],
                "weight": (values[weight_base] / base_total) if base_total else 0.0,
            }

        # --- Sección 1: pesos por ruta -------------------------------------
        routes = self.env["sng.sales.route"].search(
            ["|", ("company_id", "=", False), ("company_id", "in", company_ids)],
            order="code, name",
        )
        for index, route in enumerate(routes):
            values = by_route.get(route.id, empty)
            if not include_zero and not values[weight_base]:
                continue
            rows.append(
                dict(
                    common,
                    line_type=LINE_TYPE_ROUTE,
                    sequence=index,
                    code=route.code or "",
                    name=route.name or "",
                    sales_route_id=route.id,
                    salesperson_id=route.salesperson_id.id or None,
                    route_salesperson_name=self._get_route_salesperson_name(
                        route, by_route_salesperson.get(route.id)
                    ),
                    **_amount_values(values),
                )
            )
        unassigned = by_route.get(False, empty)
        if include_zero or unassigned[weight_base]:
            rows.append(
                dict(
                    common,
                    line_type=LINE_TYPE_ROUTE,
                    sequence=UNASSIGNED_SEQUENCE,
                    code="",
                    name=_("Sin ruta"),
                    sales_route_id=None,
                    salesperson_id=None,
                    route_salesperson_name="",
                    **_amount_values(unassigned),
                )
            )

        # --- Sección 2: pesos por vendedor ---------------------------------
        salespersons = self.env["res.partner"].search(
            [("is_salesperson", "=", True)], order="ref, name"
        )
        # Partners usados como vendedor en facturas pero no marcados como vendedor
        # (p. ej. documentos importados): se muestran igual, no se ocultan.
        orphan_ids = [
            partner_id
            for partner_id in by_salesperson
            if partner_id and partner_id not in set(salespersons.ids)
        ]
        orphans = self.env["res.partner"].browse(orphan_ids).exists()
        for index, partner in enumerate(salespersons + orphans):
            values = by_salesperson.get(partner.id, empty)
            if not include_zero and not values[weight_base]:
                continue
            rows.append(
                dict(
                    common,
                    line_type=LINE_TYPE_SALESPERSON,
                    sequence=index,
                    code=partner.ref or partner.unique_id or "",
                    name=partner.name or "",
                    sales_route_id=None,
                    salesperson_id=partner.id,
                    route_salesperson_name="",
                    **_amount_values(values),
                )
            )

        no_salesperson = by_salesperson.get(False, empty)
        if include_zero or no_salesperson[weight_base]:
            rows.append(
                dict(
                    common,
                    line_type=LINE_TYPE_SALESPERSON,
                    sequence=UNASSIGNED_SEQUENCE,
                    code="",
                    name=_("Sin vendedor"),
                    sales_route_id=None,
                    salesperson_id=None,
                    route_salesperson_name="",
                    **_amount_values(no_salesperson),
                )
            )

        # Auxiliar por cliente, con el mismo rango y las mismas compañías.
        self.env["sng.sales.route.client.report"]._rebuild_snapshot(
            date_from, date_to, company_ids
        )

        if rows:
            columns = list(self._COLUMNS.keys())
            self._cr.executemany(
                'INSERT INTO "%s" (%s) VALUES (%s)'
                % (
                    self._table,
                    ", ".join('"%s"' % col for col in columns),
                    ", ".join(["%s"] * len(columns)),
                ),
                [tuple(row[col] for col in columns) for row in rows],
            )
        self.invalidate_model()
        return True

    # ------------------------------------------------------------------
    # Exportación a Excel
    # ------------------------------------------------------------------
    @api.model
    def _get_xlsx_action(
        self, date_from, date_to, include_zero=True, include_detail=True,
        weight_base=WEIGHT_BASE_TOTAL,
    ):
        return {
            "type": "ir.actions.report",
            "data": {
                "model": self._name,
                "options": json.dumps(
                    {
                        "date_from": fields.Date.to_string(date_from),
                        "date_to": fields.Date.to_string(date_to),
                        "include_zero": include_zero,
                        "include_detail": include_detail,
                        "weight_base": weight_base,
                    },
                    default=json_default,
                ),
                "output_format": "xlsx",
                "report_name": "ventas_por_ruta_%s_%s"
                % (fields.Date.to_string(date_from), fields.Date.to_string(date_to)),
            },
            "report_type": "sng_sales_route_sales_xlsx",
        }

    def get_xlsx_report(self, options, response):
        date_from = fields.Date.to_date(options.get("date_from"))
        date_to = fields.Date.to_date(options.get("date_to"))
        weight_base = options.get("weight_base") or WEIGHT_BASE_TOTAL
        records = self.search(self._get_snapshot_domain())

        company = self.env.company
        currency_symbol = company.currency_id.symbol or ""
        amount_format = "%s#,##0;-%s#,##0" % (currency_symbol, currency_symbol)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        formats = {
            "company": workbook.add_format({"bold": True, "font_size": 12}),
            "period": workbook.add_format({"bold": True}),
            "section": workbook.add_format(
                {"bold": True, "bg_color": "#FFFF00", "border": 1, "align": "center"}
            ),
            "header": workbook.add_format(
                {"bold": True, "bg_color": "#D9E2F3", "border": 1, "align": "center"}
            ),
            "text": workbook.add_format({"border": 1}),
            "amount": workbook.add_format({"border": 1, "num_format": amount_format}),
            "weight": workbook.add_format(
                {"border": 1, "bold": True, "num_format": "0.00%", "align": "center"}
            ),
            "total_label": workbook.add_format(
                {"bold": True, "border": 1, "align": "center"}
            ),
            "total_amount": workbook.add_format(
                {"bold": True, "border": 1, "num_format": amount_format}
            ),
            "total_weight": workbook.add_format(
                {"bold": True, "border": 1, "num_format": "0.00%", "align": "center"}
            ),
        }

        self._write_xlsx_summary_sheet(
            workbook, formats, records, date_from, date_to, weight_base
        )
        if options.get("include_detail", True):
            self._write_xlsx_client_sheet(workbook, formats, date_from, date_to)

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()

    def _write_xlsx_summary_sheet(
        self, workbook, formats, records, date_from, date_to, weight_base
    ):
        """Hoja principal: pesos por ruta y pesos por vendedor."""
        company = self.env.company
        sheet = workbook.add_worksheet(_("Pesos"))
        for col, width in enumerate((14, 34, 20, 20, 11, 26)):
            sheet.set_column(col, col, width)

        row = 0
        sheet.write(row, 0, company.name or "", formats["company"])
        row += 1
        sheet.write(row, 0, _("VENTAS"), formats["period"])
        sheet.write(
            row,
            1,
            _("Del día %(date_from)s al %(date_to)s")
            % {
                "date_from": fields.Date.to_string(date_from),
                "date_to": fields.Date.to_string(date_to),
            },
            formats["period"],
        )
        sheet.write(row, 4, _("MONEDA LOCAL"), formats["period"])
        row += 1
        base_label = (
            _("Ventas Netas IVAI")
            if weight_base == WEIGHT_BASE_TOTAL
            else _("Ventas Brutas A.I")
        )
        sheet.write(row, 0, _("Peso %% calculado sobre: %s") % base_label)
        row += 2

        sections = [
            (
                LINE_TYPE_ROUTE,
                _("PESOS POR RUTA"),
                [_("COD_RUTA"), _("RUTA")],
                _("VENDEDOR"),
            ),
            (
                LINE_TYPE_SALESPERSON,
                _("PESOS POR VENDEDOR"),
                [_("COD"), _("VENDEDOR")],
                "",
            ),
        ]
        for line_type, section_title, headers, last_header in sections:
            lines = records.filtered(lambda r: r.line_type == line_type)
            sheet.merge_range(row, 0, row, 5, section_title, formats["section"])
            row += 1
            labels = headers + [
                _("Ventas Netas IVAI"),
                _("Ventas Brutas A.I"),
                _("Peso %"),
                last_header,
            ]
            for col_idx, label in enumerate(labels):
                sheet.write(row, col_idx, label, formats["header"])
            row += 1

            first_data_row = row
            for line in lines:
                sheet.write(row, 0, line.code or "", formats["text"])
                sheet.write(row, 1, line.name or "", formats["text"])
                sheet.write(row, 2, line.amount_total, formats["amount"])
                sheet.write(row, 3, line.amount_untaxed, formats["amount"])
                sheet.write(row, 4, line.weight, formats["weight"])
                sheet.write(
                    row,
                    5,
                    line.route_salesperson_name or ""
                    if line_type == LINE_TYPE_ROUTE
                    else "",
                    formats["text"],
                )
                row += 1

            sheet.merge_range(row, 0, row, 1, _("TOTAL"), formats["total_label"])
            if row > first_data_row:
                for col_idx, letter in ((2, "C"), (3, "D")):
                    sheet.write_formula(
                        row,
                        col_idx,
                        "=SUM(%s%s:%s%s)" % (letter, first_data_row + 1, letter, row),
                        formats["total_amount"],
                    )
                sheet.write_formula(
                    row,
                    4,
                    "=SUM(E%s:E%s)" % (first_data_row + 1, row),
                    formats["total_weight"],
                )
            else:
                sheet.write(row, 2, 0, formats["total_amount"])
                sheet.write(row, 3, 0, formats["total_amount"])
                sheet.write(row, 4, 0, formats["total_weight"])
            sheet.write(row, 5, "", formats["total_label"])
            row += 3

    def _write_xlsx_client_sheet(self, workbook, formats, date_from, date_to):
        """Hoja auxiliar: una línea por cliente, al estilo del reporte de gerencia."""
        client_model = self.env["sng.sales.route.client.report"]
        lines = client_model.search(client_model._get_snapshot_domain())
        company = self.env.company
        sheet = workbook.add_worksheet(_("Ventas por cliente"))

        columns = [
            (_("codigo"), 12, "partner_code", "text"),
            (_("Cliente"), 42, "partner_name", "text"),
            (_("Ventas Netas IVAI"), 20, "amount_total", "amount"),
            (_("Ventas Brutas A.I"), 20, "amount_untaxed", "amount"),
            (_("cod Ruta"), 11, "route_code", "text"),
            (_("Ruta"), 26, "route_name", "text"),
            (_("Cod Vend"), 11, "salesperson_code", "text"),
            (_("Vendedor"), 26, "salesperson_name", "text"),
        ]
        for col_idx, (_label, width, _key, _fmt) in enumerate(columns):
            sheet.set_column(col_idx, col_idx, width)

        sheet.write(0, 0, company.name or "", formats["company"])
        sheet.write(
            0,
            5,
            _("Fecha : %s") % fields.Datetime.to_string(fields.Datetime.now()),
            formats["period"],
        )
        sheet.write(1, 0, _("VENTAS"), formats["period"])
        sheet.write(
            1,
            2,
            _("Del día %(date_from)s al %(date_to)s")
            % {
                "date_from": fields.Date.to_string(date_from),
                "date_to": fields.Date.to_string(date_to),
            },
            formats["period"],
        )
        sheet.write(1, 5, _("MONEDA LOCAL"), formats["period"])

        header_row = 2
        for col_idx, (label, _width, _key, _fmt) in enumerate(columns):
            sheet.write(header_row, col_idx, label, formats["header"])

        row = header_row + 1
        first_data_row = row
        for line in lines:
            for col_idx, (_label, _width, key, fmt_key) in enumerate(columns):
                value = line[key]
                if value in (False, None):
                    value = ""
                sheet.write(row, col_idx, value, formats[fmt_key])
            row += 1

        sheet.merge_range(row, 0, row, 1, _("TOTAL GENERAL :"), formats["total_label"])
        if row > first_data_row:
            for col_idx, letter in ((2, "C"), (3, "D")):
                sheet.write_formula(
                    row,
                    col_idx,
                    "=SUM(%s%s:%s%s)" % (letter, first_data_row + 1, letter, row),
                    formats["total_amount"],
                )
        else:
            sheet.write(row, 2, 0, formats["total_amount"])
            sheet.write(row, 3, 0, formats["total_amount"])
        for col_idx in range(4, len(columns)):
            sheet.write(row, col_idx, "", formats["total_label"])
        sheet.freeze_panes(header_row + 1, 0)
