# -*- coding: utf-8 -*-

from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SngNewReactivatedCustomerReport(models.Model):
    _name = "sng.new.reactivated.customer.report"
    _description = "Reporte Clientes Nuevos-React"
    _order = "last_invoice_date desc, partner_name"
    _rec_name = "partner_id"

    run_user_id = fields.Many2one("res.users", string="Usuario corrida", readonly=True, index=True)
    generated_at = fields.Datetime(string="Generado el", readonly=True)
    date_from = fields.Date(string="Fecha desde", readonly=True, index=True)
    date_to = fields.Date(string="Fecha hasta", readonly=True, index=True)
    inactivity_months = fields.Integer(string="Meses sin compra", readonly=True)
    report_type = fields.Selection(
        [
            ("new", "Nuevo"),
            ("reactivated", "Reactivado"),
        ],
        string="Tipo",
        readonly=True,
        index=True,
    )

    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True, index=True)
    partner_code = fields.Char(string="Codigo", readonly=True, index=True)
    partner_name = fields.Char(string="Nombre", readonly=True, index=True)
    partner_create_date = fields.Date(string="Fecha de creacion", readonly=True, index=True)
    sales_route_id = fields.Many2one("sng.sales.route", string="Ruta", readonly=True, index=True)
    salesperson_id = fields.Many2one("res.partner", string="Vendedor", readonly=True, index=True)
    company_id = fields.Many2one("res.company", string="Compania", readonly=True, index=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)

    previous_invoice_id = fields.Many2one("account.move", string="Factura anterior", readonly=True)
    previous_invoice_date = fields.Date(string="Fecha factura anterior", readonly=True, index=True)
    previous_invoice_amount = fields.Monetary(
        string="Monto factura anterior",
        currency_field="currency_id",
        readonly=True,
    )
    last_invoice_id = fields.Many2one("account.move", string="Ultima factura", readonly=True)
    last_invoice_date = fields.Date(string="Fecha ultima factura", readonly=True, index=True)
    last_invoice_amount = fields.Monetary(
        string="Monto ultima factura",
        currency_field="currency_id",
        readonly=True,
    )

    @api.model
    def _get_allowed_company_ids(self):
        return self.env.context.get("allowed_company_ids") or self.env.companies.ids

    @api.model
    def _normalize_month(self, month_date, inactivity_months):
        month_date = fields.Date.to_date(month_date)
        if not month_date:
            raise UserError(_("Debe indicar el mes del reporte."))
        if inactivity_months <= 0:
            raise UserError(_("Los meses sin compra deben ser mayores a cero."))

        date_from = month_date.replace(day=1)
        date_to = date_from + relativedelta(day=31)
        threshold_date = date_from - relativedelta(months=inactivity_months)
        start_dt = datetime.combine(date_from, time.min)
        end_dt = datetime.combine(date_to, time.max)
        return date_from, date_to, threshold_date, start_dt, end_dt

    @api.model
    def _get_snapshot_domain(self, date_from=None, date_to=None, user_id=None):
        domain = [("run_user_id", "=", user_id or self.env.user.id)]
        if date_from:
            domain.append(("date_from", "=", fields.Date.to_date(date_from)))
        if date_to:
            domain.append(("date_to", "=", fields.Date.to_date(date_to)))
        company_ids = self._get_allowed_company_ids()
        if company_ids:
            domain.append(("company_id", "in", company_ids))
        return domain

    @api.model
    def _cleanup_previous_snapshot(self, run_user_id):
        self.sudo().search([("run_user_id", "=", run_user_id)]).unlink()

    @api.model
    def _rebuild_snapshot(self, month_date, inactivity_months=6, company_ids=None):
        date_from, date_to, threshold_date, start_dt, end_dt = self._normalize_month(
            month_date,
            inactivity_months,
        )
        company_ids = company_ids or self._get_allowed_company_ids()
        if not company_ids:
            raise UserError(_("No hay companias activas para generar el reporte."))

        default_company_id = company_ids[0]
        run_user_id = self.env.user.id
        generated_at = fields.Datetime.now()
        self._cleanup_previous_snapshot(run_user_id)

        self.env["account.move"].flush_model([
            "commercial_partner_id",
            "company_id",
            "invoice_date",
            "move_type",
            "state",
            "amount_total_signed",
        ])
        self.env["res.partner"].flush_model([
            "commercial_partner_id",
            "company_id",
            "create_date",
            "customer_rank",
            "unique_id",
            "name",
            "sales_route_id",
            "assigned_salesperson_id",
        ])

        self.env.cr.execute(
            """
                INSERT INTO sng_new_reactivated_customer_report (
                    run_user_id,
                    generated_at,
                    date_from,
                    date_to,
                    inactivity_months,
                    report_type,
                    partner_id,
                    partner_code,
                    partner_name,
                    partner_create_date,
                    sales_route_id,
                    salesperson_id,
                    company_id,
                    currency_id,
                    previous_invoice_id,
                    previous_invoice_date,
                    previous_invoice_amount,
                    last_invoice_id,
                    last_invoice_date,
                    last_invoice_amount,
                    create_uid,
                    create_date,
                    write_uid,
                    write_date
                )
                WITH current_invoice AS (
                    SELECT DISTINCT ON (am.commercial_partner_id, am.company_id)
                        am.commercial_partner_id AS partner_id,
                        am.company_id,
                        am.id AS invoice_id,
                        am.invoice_date,
                        am.amount_total_signed AS amount_total
                    FROM account_move am
                    WHERE am.state = 'posted'
                      AND am.move_type = 'out_invoice'
                      AND am.invoice_date >= %s
                      AND am.invoice_date <= %s
                      AND am.company_id = ANY(%s)
                      AND am.commercial_partner_id IS NOT NULL
                    ORDER BY
                        am.commercial_partner_id,
                        am.company_id,
                        am.invoice_date DESC,
                        am.id DESC
                ),
                previous_invoice AS (
                    SELECT DISTINCT ON (am.commercial_partner_id, am.company_id)
                        am.commercial_partner_id AS partner_id,
                        am.company_id,
                        am.id AS invoice_id,
                        am.invoice_date,
                        am.amount_total_signed AS amount_total
                    FROM account_move am
                    WHERE am.state = 'posted'
                      AND am.move_type = 'out_invoice'
                      AND am.invoice_date < %s
                      AND am.company_id = ANY(%s)
                      AND am.commercial_partner_id IS NOT NULL
                    ORDER BY
                        am.commercial_partner_id,
                        am.company_id,
                        am.invoice_date DESC,
                        am.id DESC
                ),
                new_rows AS (
                    SELECT DISTINCT ON (rp.id, COALESCE(ci.company_id, rp.company_id, %s))
                        %s::integer AS run_user_id,
                        %s::timestamp AS generated_at,
                        %s::date AS date_from,
                        %s::date AS date_to,
                        %s::integer AS inactivity_months,
                        'new' AS report_type,
                        rp.id AS partner_id,
                        COALESCE(rp.unique_id, '') AS partner_code,
                        COALESCE(rp.name, '') AS partner_name,
                        rp.create_date::date AS partner_create_date,
                        rp.sales_route_id,
                        rp.assigned_salesperson_id AS salesperson_id,
                        COALESCE(ci.company_id, rp.company_id, %s) AS company_id,
                        rc.currency_id,
                        pi.invoice_id AS previous_invoice_id,
                        pi.invoice_date AS previous_invoice_date,
                        pi.amount_total AS previous_invoice_amount,
                        ci.invoice_id AS last_invoice_id,
                        ci.invoice_date AS last_invoice_date,
                        ci.amount_total AS last_invoice_amount,
                        %s::integer AS create_uid,
                        %s::timestamp AS create_date,
                        %s::integer AS write_uid,
                        %s::timestamp AS write_date
                    FROM res_partner rp
                    LEFT JOIN current_invoice ci
                        ON ci.partner_id = rp.id
                    LEFT JOIN previous_invoice pi
                        ON pi.partner_id = rp.id
                       AND pi.company_id = COALESCE(ci.company_id, rp.company_id, %s)
                    JOIN res_company rc
                        ON rc.id = COALESCE(ci.company_id, rp.company_id, %s)
                    WHERE rp.id = rp.commercial_partner_id
                      AND rp.customer_rank > 0
                      AND rp.create_date >= %s
                      AND rp.create_date <= %s
                      AND (rp.company_id IS NULL OR rp.company_id = ANY(%s))
                    ORDER BY
                        rp.id,
                        COALESCE(ci.company_id, rp.company_id, %s),
                        ci.invoice_date DESC NULLS LAST,
                        ci.invoice_id DESC NULLS LAST
                ),
                reactivated_rows AS (
                    SELECT
                        %s::integer AS run_user_id,
                        %s::timestamp AS generated_at,
                        %s::date AS date_from,
                        %s::date AS date_to,
                        %s::integer AS inactivity_months,
                        'reactivated' AS report_type,
                        rp.id AS partner_id,
                        COALESCE(rp.unique_id, '') AS partner_code,
                        COALESCE(rp.name, '') AS partner_name,
                        rp.create_date::date AS partner_create_date,
                        rp.sales_route_id,
                        rp.assigned_salesperson_id AS salesperson_id,
                        ci.company_id,
                        rc.currency_id,
                        pi.invoice_id AS previous_invoice_id,
                        pi.invoice_date AS previous_invoice_date,
                        pi.amount_total AS previous_invoice_amount,
                        ci.invoice_id AS last_invoice_id,
                        ci.invoice_date AS last_invoice_date,
                        ci.amount_total AS last_invoice_amount,
                        %s::integer AS create_uid,
                        %s::timestamp AS create_date,
                        %s::integer AS write_uid,
                        %s::timestamp AS write_date
                    FROM current_invoice ci
                    JOIN previous_invoice pi
                        ON pi.partner_id = ci.partner_id
                       AND pi.company_id = ci.company_id
                    JOIN res_partner rp
                        ON rp.id = ci.partner_id
                    JOIN res_company rc
                        ON rc.id = ci.company_id
                    LEFT JOIN new_rows nr
                        ON nr.partner_id = rp.id
                       AND nr.company_id = ci.company_id
                    WHERE pi.invoice_date <= %s
                      AND nr.partner_id IS NULL
                )
                SELECT * FROM new_rows
                UNION ALL
                SELECT * FROM reactivated_rows
            """,
            [
                date_from,
                date_to,
                company_ids,
                date_from,
                company_ids,
                default_company_id,
                run_user_id,
                generated_at,
                date_from,
                date_to,
                inactivity_months,
                default_company_id,
                run_user_id,
                generated_at,
                run_user_id,
                generated_at,
                default_company_id,
                default_company_id,
                fields.Datetime.to_string(start_dt),
                fields.Datetime.to_string(end_dt),
                company_ids,
                default_company_id,
                run_user_id,
                generated_at,
                date_from,
                date_to,
                inactivity_months,
                run_user_id,
                generated_at,
                run_user_id,
                generated_at,
                threshold_date,
            ],
        )
        return date_from, date_to

    def action_open_partner(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.partner_id.display_name,
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.partner_id.id,
            "target": "current",
        }

    def action_open_last_invoice(self):
        self.ensure_one()
        if not self.last_invoice_id:
            raise UserError(_("Este cliente no tiene ultima factura en el mes seleccionado."))
        return {
            "type": "ir.actions.act_window",
            "name": self.last_invoice_id.name,
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.last_invoice_id.id,
            "target": "current",
        }
