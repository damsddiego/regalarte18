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
        help="Vendedor configurado en la ruta. Solo aplica a la sección de rutas.",
    )
    amount_untaxed = fields.Monetary(
        string="Ventas Brutas A.I",
        readonly=True,
        currency_field="currency_id",
        help="Suma del importe sin impuestos de facturas menos notas de crédito publicadas.",
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
        "amount_untaxed": "NUMERIC",
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
        """Devuelve (por_ruta, por_vendedor, total) leyendo las facturas del rango."""
        self._cr.execute(
            """
            SELECT am.sales_route_id AS route_id,
                   am.salesperson_id AS salesperson_id,
                   SUM(am.amount_untaxed_signed) AS amount,
                   COUNT(*) AS doc_count
              FROM account_move am
             WHERE am.move_type IN %s
               AND am.state = 'posted'
               AND am.invoice_date >= %s
               AND am.invoice_date <= %s
               AND am.company_id IN %s
          GROUP BY am.sales_route_id, am.salesperson_id
            """,
            (SALE_MOVE_TYPES, date_from, date_to, tuple(company_ids)),
        )
        by_route = {}
        by_salesperson = {}
        total = 0.0
        for row in self._cr.dictfetchall():
            amount = float(row["amount"] or 0.0)
            count = row["doc_count"] or 0
            route_key = row["route_id"] or False
            salesperson_key = row["salesperson_id"] or False
            route_amount, route_count = by_route.get(route_key, (0.0, 0))
            by_route[route_key] = (route_amount + amount, route_count + count)
            sp_amount, sp_count = by_salesperson.get(salesperson_key, (0.0, 0))
            by_salesperson[salesperson_key] = (sp_amount + amount, sp_count + count)
            total += amount
        return by_route, by_salesperson, total

    # ------------------------------------------------------------------
    # Construcción del snapshot
    # ------------------------------------------------------------------
    @api.model
    def _rebuild_snapshot(self, date_from, date_to, include_zero=True):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            raise UserError(_("Debe indicar la fecha inicial y la fecha final."))
        if date_from > date_to:
            raise UserError(_("La fecha inicial no puede ser posterior a la fecha final."))

        company_ids = self._get_allowed_company_ids()
        if not company_ids:
            raise UserError(_("No hay compañías activas para generar el reporte."))

        user = self.env.user
        company = self.env.company
        self._cr.execute(
            'DELETE FROM "%s" WHERE user_id = %%s' % self._table, (user.id,)
        )

        by_route, by_salesperson, total = self._get_amounts(
            date_from, date_to, company_ids
        )

        common = {
            "user_id": user.id,
            "date_from": date_from,
            "date_to": date_to,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
        }
        rows = []

        # --- Sección 1: pesos por ruta -------------------------------------
        routes = self.env["sng.sales.route"].search(
            ["|", ("company_id", "=", False), ("company_id", "in", company_ids)],
            order="code, name",
        )
        for index, route in enumerate(routes):
            amount, count = by_route.get(route.id, (0.0, 0))
            if not include_zero and not amount:
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
                    route_salesperson_name=route.salesperson_id.name or "",
                    amount_untaxed=amount,
                    weight=(amount / total) if total else 0.0,
                    invoice_count=count,
                )
            )
        unassigned_amount, unassigned_count = by_route.get(False, (0.0, 0))
        if include_zero or unassigned_amount:
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
                    amount_untaxed=unassigned_amount,
                    weight=(unassigned_amount / total) if total else 0.0,
                    invoice_count=unassigned_count,
                )
            )

        # --- Sección 2: pesos por vendedor ---------------------------------
        salespersons = self.env["res.partner"].search(
            [("is_salesperson", "=", True)], order="ref, name"
        )
        for index, salesperson in enumerate(salespersons):
            amount, count = by_salesperson.get(salesperson.id, (0.0, 0))
            if not include_zero and not amount:
                continue
            rows.append(
                dict(
                    common,
                    line_type=LINE_TYPE_SALESPERSON,
                    sequence=index,
                    code=salesperson.ref or salesperson.unique_id or "",
                    name=salesperson.name or "",
                    sales_route_id=None,
                    salesperson_id=salesperson.id,
                    route_salesperson_name="",
                    amount_untaxed=amount,
                    weight=(amount / total) if total else 0.0,
                    invoice_count=count,
                )
            )
        # Partners usados como vendedor en facturas pero no marcados como vendedor
        # (p. ej. documentos importados): se muestran igual, no se ocultan.
        known_ids = set(salespersons.ids)
        orphan_ids = [
            partner_id
            for partner_id in by_salesperson
            if partner_id and partner_id not in known_ids
        ]
        orphans = self.env["res.partner"].browse(orphan_ids).exists()
        for index, partner in enumerate(orphans, start=len(salespersons)):
            amount, count = by_salesperson.get(partner.id, (0.0, 0))
            if not amount and not include_zero:
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
                    amount_untaxed=amount,
                    weight=(amount / total) if total else 0.0,
                    invoice_count=count,
                )
            )

        no_salesperson_amount, no_salesperson_count = by_salesperson.get(False, (0.0, 0))
        if include_zero or no_salesperson_amount:
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
                    amount_untaxed=no_salesperson_amount,
                    weight=(no_salesperson_amount / total) if total else 0.0,
                    invoice_count=no_salesperson_count,
                )
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
    def _get_xlsx_action(self, date_from, date_to, include_zero=True):
        return {
            "type": "ir.actions.report",
            "data": {
                "model": self._name,
                "options": json.dumps(
                    {
                        "date_from": fields.Date.to_string(date_from),
                        "date_to": fields.Date.to_string(date_to),
                        "include_zero": include_zero,
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
        records = self.search(self._get_snapshot_domain())

        company = self.env.company
        currency_symbol = company.currency_id.symbol or ""
        amount_format = '%s#,##0;-%s#,##0' % (currency_symbol, currency_symbol)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Ventas por Ruta"))

        company_fmt = workbook.add_format({"bold": True, "font_size": 12})
        period_fmt = workbook.add_format({"bold": True})
        section_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#FFFF00", "border": 1, "align": "center"}
        )
        header_fmt = workbook.add_format(
            {"bold": True, "bg_color": "#D9E2F3", "border": 1, "align": "center"}
        )
        text_fmt = workbook.add_format({"border": 1})
        amount_fmt = workbook.add_format({"border": 1, "num_format": amount_format})
        weight_fmt = workbook.add_format(
            {"border": 1, "bold": True, "num_format": "0.00%", "align": "center"}
        )
        total_label_fmt = workbook.add_format(
            {"bold": True, "border": 1, "align": "center"}
        )
        total_amount_fmt = workbook.add_format(
            {"bold": True, "border": 1, "num_format": amount_format}
        )
        total_weight_fmt = workbook.add_format(
            {"bold": True, "border": 1, "num_format": "0.00%", "align": "center"}
        )

        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 32)
        sheet.set_column(2, 2, 22)
        sheet.set_column(3, 3, 12)
        sheet.set_column(4, 4, 24)

        row = 0
        sheet.write(row, 0, company.name or "", company_fmt)
        row += 1
        sheet.write(row, 0, _("VENTAS"), period_fmt)
        sheet.write(
            row,
            1,
            "%s - %s"
            % (fields.Date.to_string(date_from), fields.Date.to_string(date_to)),
            period_fmt,
        )
        row += 2

        sections = [
            (
                LINE_TYPE_ROUTE,
                _("PESOS POR RUTA"),
                [_("COD_RUTA"), _("RUTA"), _("VENTAS Brutas A.I"), _("Peso %"), _("VENDEDOR")],
            ),
            (
                LINE_TYPE_SALESPERSON,
                _("PESOS POR VENDEDOR"),
                [_("COD"), _("VENDEDOR"), _("VENTAS"), _("Peso %"), ""],
            ),
        ]

        for line_type, section_title, headers in sections:
            lines = records.filtered(lambda r: r.line_type == line_type)
            sheet.merge_range(row, 0, row, 4, section_title, section_fmt)
            row += 1
            for col_idx, label in enumerate(headers):
                sheet.write(row, col_idx, label, header_fmt)
            row += 1

            first_data_row = row
            for line in lines:
                sheet.write(row, 0, line.code or "", text_fmt)
                sheet.write(row, 1, line.name or "", text_fmt)
                sheet.write(row, 2, line.amount_untaxed, amount_fmt)
                sheet.write(row, 3, line.weight, weight_fmt)
                sheet.write(
                    row,
                    4,
                    line.route_salesperson_name or "" if line_type == LINE_TYPE_ROUTE else "",
                    text_fmt,
                )
                row += 1

            sheet.merge_range(row, 0, row, 1, _("TOTAL"), total_label_fmt)
            if row > first_data_row:
                sheet.write_formula(
                    row,
                    2,
                    "=SUM(C%s:C%s)" % (first_data_row + 1, row),
                    total_amount_fmt,
                )
                sheet.write_formula(
                    row,
                    3,
                    "=SUM(D%s:D%s)" % (first_data_row + 1, row),
                    total_weight_fmt,
                )
            else:
                sheet.write(row, 2, 0, total_amount_fmt)
                sheet.write(row, 3, 0, total_weight_fmt)
            sheet.write(row, 4, "", total_label_fmt)
            row += 3

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
