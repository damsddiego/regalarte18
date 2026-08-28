# -*- coding: utf-8 -*-

from odoo import _, api, fields, models

from .sales_route_sales_report import SALE_MOVE_TYPES, _ensure_backing_table


class SngSalesRouteClientReport(models.Model):
    """Auxiliar del reporte de ventas: una línea por cliente."""

    _name = "sng.sales.route.client.report"
    _description = "Ventas por Cliente (auxiliar de rutas)"
    _auto = False
    _rec_name = "partner_name"
    _order = "amount_total desc, partner_name"

    user_id = fields.Many2one("res.users", string="Usuario", readonly=True)
    date_from = fields.Date(string="Desde", readonly=True)
    date_to = fields.Date(string="Hasta", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)

    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    partner_code = fields.Char(string="Código", readonly=True)
    partner_name = fields.Char(string="Cliente", readonly=True)
    sales_route_id = fields.Many2one("sng.sales.route", string="Ruta", readonly=True)
    route_code = fields.Char(string="Cód. ruta", readonly=True)
    route_name = fields.Char(string="Ruta", readonly=True)
    salesperson_id = fields.Many2one("res.partner", string="Vendedor", readonly=True)
    salesperson_code = fields.Char(string="Cód. vendedor", readonly=True)
    salesperson_name = fields.Char(string="Vendedor", readonly=True)

    amount_total = fields.Monetary(
        string="Ventas Netas IVAI",
        readonly=True,
        currency_field="currency_id",
        help="Total facturado con impuestos incluidos (las notas de crédito restan).",
    )
    amount_untaxed = fields.Monetary(
        string="Ventas Brutas A.I",
        readonly=True,
        currency_field="currency_id",
        help="Total facturado sin impuestos (las notas de crédito restan).",
    )
    invoice_count = fields.Integer(string="Documentos", readonly=True)

    _COLUMNS = {
        "user_id": "INTEGER NOT NULL",
        "date_from": "DATE",
        "date_to": "DATE",
        "company_id": "INTEGER",
        "currency_id": "INTEGER",
        "partner_id": "INTEGER",
        "partner_code": "VARCHAR",
        "partner_name": "VARCHAR",
        "sales_route_id": "INTEGER",
        "route_code": "VARCHAR",
        "route_name": "VARCHAR",
        "salesperson_id": "INTEGER",
        "salesperson_code": "VARCHAR",
        "salesperson_name": "VARCHAR",
        "amount_total": "NUMERIC",
        "amount_untaxed": "NUMERIC",
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
            CREATE INDEX IF NOT EXISTS sng_sales_route_client_report_user_idx
                ON sng_sales_route_client_report (user_id);
            """
        )

    @api.model
    def _get_snapshot_domain(self):
        return [("user_id", "=", self.env.user.id)]

    @api.model
    def _rebuild_snapshot(self, date_from, date_to, company_ids):
        """Reconstruye el auxiliar por cliente para el usuario actual."""
        user = self.env.user
        company = self.env.company
        self._cr.execute(
            'DELETE FROM "%s" WHERE user_id = %%s' % self._table, (user.id,)
        )
        self._cr.execute(
            """
            INSERT INTO "%s" (
                user_id, date_from, date_to, company_id, currency_id,
                partner_id, partner_code, partner_name,
                sales_route_id, route_code, route_name,
                salesperson_id, salesperson_code, salesperson_name,
                amount_total, amount_untaxed, invoice_count
            )
            SELECT %%s, %%s, %%s, %%s, %%s,
                   rp.id,
                   rp.unique_id,
                   rp.name,
                   am.sales_route_id,
                   route.code,
                   COALESCE(route.name->>'es_CR', route.name->>'en_US', %%s),
                   sp.id,
                   COALESCE(sp.ref, sp.unique_id),
                   COALESCE(sp.name, %%s),
                   SUM(am.amount_total_signed),
                   SUM(am.amount_untaxed_signed),
                   COUNT(*)
              FROM account_move am
              JOIN res_partner rp ON rp.id = am.commercial_partner_id
              LEFT JOIN sng_sales_route route ON route.id = am.sales_route_id
              LEFT JOIN res_partner sp
                     ON sp.id = COALESCE(am.assigned_salesperson_id, am.salesperson_id)
             WHERE am.move_type IN %%s
               AND am.state = 'posted'
               AND am.invoice_date >= %%s
               AND am.invoice_date <= %%s
               AND am.company_id IN %%s
          GROUP BY rp.id, rp.unique_id, rp.name,
                   am.sales_route_id, route.code, route.name,
                   sp.id, sp.ref, sp.unique_id, sp.name
            """
            % self._table,
            (
                user.id,
                date_from,
                date_to,
                company.id,
                company.currency_id.id,
                _("Sin ruta"),
                _("Sin vendedor"),
                SALE_MOVE_TYPES,
                date_from,
                date_to,
                tuple(company_ids),
            ),
        )
        self.invalidate_model()
        return True

    def action_view_moves(self):
        """Abre las facturas y notas de crédito del cliente en la línea."""
        self.ensure_one()
        report_model = self.env["sng.sales.route.sales.report"]
        domain = report_model._get_base_domain(self.date_from, self.date_to) + [
            ("commercial_partner_id", "=", self.partner_id.id),
            ("sales_route_id", "=", self.sales_route_id.id or False),
        ]
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos: %s") % (self.partner_name or ""),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": domain,
            "context": {"create": False},
        }
