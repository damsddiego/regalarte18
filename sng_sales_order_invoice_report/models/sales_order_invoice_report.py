# -*- coding: utf-8 -*-

from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.addons.sale.models.sale_order import INVOICE_STATUS, SALE_ORDER_STATE
from odoo.exceptions import UserError
from odoo.osv import expression


class SngSalesOrderInvoiceReport(models.Model):
    _name = "sng.sales.order.invoice.report"
    _description = "Reporte Ventas Ingresadas vs No Facturadas vs Facturadas"
    _order = "order_create_date desc, id desc"
    _rec_name = "order_name"

    run_user_id = fields.Many2one("res.users", string="Usuario corrida", readonly=True, index=True)
    generated_at = fields.Datetime(string="Generado el", readonly=True)
    date_from = fields.Date(string="Fecha desde", readonly=True, index=True)
    date_to = fields.Date(string="Fecha hasta", readonly=True, index=True)

    sale_order_id = fields.Many2one("sale.order", string="Orden de venta", readonly=True, index=True)
    sale_order_line_id = fields.Many2one("sale.order.line", string="Linea de orden", readonly=True, index=True)
    order_name = fields.Char(string="Orden", readonly=True)
    order_create_date = fields.Datetime(string="Fecha ingreso sistema", readonly=True, index=True)
    order_date = fields.Datetime(string="Fecha orden", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True, index=True)
    salesperson_id = fields.Many2one("res.partner", string="Vendedor", readonly=True, index=True)
    company_id = fields.Many2one("res.company", string="Compania", readonly=True, index=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)
    product_id = fields.Many2one("product.product", string="Producto", readonly=True, index=True)
    categ_id = fields.Many2one("product.category", string="Categoria", readonly=True, index=True)

    order_state = fields.Selection(SALE_ORDER_STATE, string="Estado orden", readonly=True)
    order_invoice_status = fields.Selection(INVOICE_STATUS, string="Estado facturacion orden", readonly=True)
    line_invoice_status = fields.Selection(INVOICE_STATUS, string="Estado facturacion linea", readonly=True)

    ordered_qty = fields.Float(string="Cant. ingresada", readonly=True, digits="Product Unit of Measure")
    ordered_untaxed = fields.Monetary(string="Subtotal ingresado", readonly=True, currency_field="currency_id")
    ordered_total = fields.Monetary(string="Total ingresado", readonly=True, currency_field="currency_id")

    pending_qty = fields.Float(string="Cant. no facturada", readonly=True, digits="Product Unit of Measure")
    pending_untaxed = fields.Monetary(string="Subtotal no facturado", readonly=True, currency_field="currency_id")
    pending_total = fields.Monetary(string="Total no facturado", readonly=True, currency_field="currency_id")

    invoiced_qty = fields.Float(string="Cant. facturada", readonly=True, digits="Product Unit of Measure")
    invoiced_untaxed = fields.Monetary(string="Subtotal facturado", readonly=True, currency_field="currency_id")
    invoiced_total = fields.Monetary(string="Total facturado", readonly=True, currency_field="currency_id")

    @api.model
    def _get_allowed_company_ids(self):
        return self.env.context.get("allowed_company_ids") or self.env.companies.ids

    @api.model
    def _get_snapshot_domain(self, date_from=None, date_to=None, user_id=None):
        domain = [("run_user_id", "=", user_id or self.env.user.id)]
        if date_from:
            domain.append(("date_from", "=", fields.Date.to_date(date_from)))
        if date_to:
            domain.append(("date_to", "=", fields.Date.to_date(date_to)))
        allowed_company_ids = self._get_allowed_company_ids()
        if allowed_company_ids:
            domain.append(("company_id", "in", allowed_company_ids))
        return domain

    @api.model
    def _normalize_date_range(self, date_from, date_to):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to:
            raise UserError(_("Debe indicar un rango de fechas valido."))
        if date_from > date_to:
            raise UserError(_("La fecha inicial debe ser menor o igual a la fecha final."))
        start_dt = datetime.combine(date_from, time.min)
        end_dt = datetime.combine(date_to, time.max)
        return date_from, date_to, start_dt, end_dt

    @api.model
    def _get_effective_salesperson(self, order):
        return order.salesperson_id or order.partner_id.assigned_salesperson_id

    @api.model
    def _convert_amount_to_company_currency(self, amount, currency, company, conversion_date):
        amount = amount or 0.0
        company_currency = company.currency_id
        if not currency or not company_currency or currency == company_currency:
            return amount
        return currency._convert(amount, company_currency, company, conversion_date)

    @api.model
    def _build_snapshot_domain(self, date_from, date_to, company_ids=None, partner_ids=None, salesperson_ids=None):
        _, _, start_dt, end_dt = self._normalize_date_range(date_from, date_to)
        company_ids = company_ids or self._get_allowed_company_ids()
        if not company_ids:
            raise UserError(_("No hay companias activas para generar el reporte."))

        domain = [
            ("order_id.state", "=", "sale"),
            ("order_id.create_date", ">=", fields.Datetime.to_string(start_dt)),
            ("order_id.create_date", "<=", fields.Datetime.to_string(end_dt)),
            ("order_id.company_id", "in", company_ids),
            ("display_type", "=", False),
            ("is_downpayment", "=", False),
        ]
        if partner_ids:
            domain.append(("order_id.partner_id", "in", partner_ids))
        if salesperson_ids:
            salesperson_domain = expression.OR([
                [("order_id.salesperson_id", "in", salesperson_ids)],
                [
                    ("order_id.salesperson_id", "=", False),
                    ("order_id.partner_id.assigned_salesperson_id", "in", salesperson_ids),
                ],
            ])
            domain = expression.AND([domain, salesperson_domain])
        return domain

    @api.model
    def _cleanup_previous_snapshot(self, run_user_id):
        self.sudo().search([("run_user_id", "=", run_user_id)]).unlink()

    @api.model
    def _prepare_snapshot_vals(self, line, run_user_id, generated_at, date_from, date_to):
        order = line.order_id
        company = order.company_id
        salesperson = self._get_effective_salesperson(order)
        conversion_date = fields.Date.to_date(order.date_order) or fields.Date.context_today(self)
        currency = company.currency_id

        ordered_untaxed = self._convert_amount_to_company_currency(
            line.price_subtotal, line.currency_id, company, conversion_date
        )
        ordered_total = self._convert_amount_to_company_currency(
            line.price_total, line.currency_id, company, conversion_date
        )
        pending_untaxed = self._convert_amount_to_company_currency(
            line.untaxed_amount_to_invoice, line.currency_id, company, conversion_date
        )
        pending_total = self._convert_amount_to_company_currency(
            line.amount_to_invoice, line.currency_id, company, conversion_date
        )
        invoiced_untaxed = self._convert_amount_to_company_currency(
            line.untaxed_amount_invoiced, line.currency_id, company, conversion_date
        )
        invoiced_total = self._convert_amount_to_company_currency(
            line.amount_invoiced, line.currency_id, company, conversion_date
        )

        return {
            "run_user_id": run_user_id,
            "generated_at": generated_at,
            "date_from": date_from,
            "date_to": date_to,
            "sale_order_id": order.id,
            "sale_order_line_id": line.id,
            "order_name": order.name,
            "order_create_date": order.create_date,
            "order_date": order.date_order,
            "partner_id": order.partner_id.id,
            "salesperson_id": salesperson.id if salesperson else False,
            "company_id": company.id,
            "currency_id": currency.id,
            "product_id": line.product_id.id if line.product_id else False,
            "categ_id": line.product_id.categ_id.id if line.product_id else False,
            "order_state": order.state,
            "order_invoice_status": order.invoice_status,
            "line_invoice_status": line.invoice_status,
            "ordered_qty": line.product_uom_qty,
            "ordered_untaxed": ordered_untaxed,
            "ordered_total": ordered_total,
            "pending_qty": line.qty_to_invoice,
            "pending_untaxed": pending_untaxed,
            "pending_total": pending_total,
            "invoiced_qty": line.qty_invoiced,
            "invoiced_untaxed": invoiced_untaxed,
            "invoiced_total": invoiced_total,
        }

    @api.model
    def _rebuild_snapshot(self, date_from, date_to, company_ids=None, partner_ids=None, salesperson_ids=None):
        date_from, date_to, _, _ = self._normalize_date_range(date_from, date_to)
        company_ids = company_ids or self._get_allowed_company_ids()
        if not company_ids:
            raise UserError(_("No hay companias activas para generar el reporte."))

        domain = self._build_snapshot_domain(
            date_from=date_from,
            date_to=date_to,
            company_ids=company_ids,
            partner_ids=partner_ids,
            salesperson_ids=salesperson_ids,
        )

        run_user_id = self.env.user.id
        generated_at = fields.Datetime.now()
        self._cleanup_previous_snapshot(run_user_id)

        line_model = self.env["sale.order.line"].sudo()
        snapshot_model = self.sudo().with_context(mail_create_nolog=True, tracking_disable=True)
        last_id = 0
        batch_size = 500

        while True:
            batch_domain = expression.AND([domain, [("id", ">", last_id)]])
            lines = line_model.search(batch_domain, order="id", limit=batch_size)
            if not lines:
                break

            vals_list = [
                self._prepare_snapshot_vals(line, run_user_id, generated_at, date_from, date_to)
                for line in lines
            ]
            if vals_list:
                snapshot_model.create(vals_list)
            last_id = lines[-1].id

    def action_open_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.order_name,
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }
