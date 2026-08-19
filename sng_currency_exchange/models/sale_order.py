# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    sng_use_custom_rate = fields.Boolean(
        string="Usar Tipo de Cambio Fijo",
        copy=False,
        help="Indica que esta orden conserva un tipo de cambio fijo tomado de la lista de precios.",
    )
    sng_custom_exchange_rate = fields.Float(
        string="Tipo de Cambio Fijo",
        digits=(16, 6),
        copy=False,
        help="Tipo de cambio expresado en moneda de la compañía por 1 unidad de moneda extranjera.",
    )

    def _sng_get_pricelist_rate_vals(self, pricelist):
        self.ensure_one()
        company = self.company_id or self.env.company
        if (
            pricelist
            and pricelist.sng_use_custom_rate
            and pricelist.sng_custom_exchange_rate > 0
            and pricelist.sng_is_usd_currency
            and pricelist.currency_id != company.currency_id
        ):
            return {
                "sng_use_custom_rate": True,
                "sng_custom_exchange_rate": pricelist.sng_custom_exchange_rate,
            }
        return {
            "sng_use_custom_rate": False,
            "sng_custom_exchange_rate": 0.0,
        }

    @api.depends("partner_id", "company_id")
    def _compute_pricelist_id(self):
        super()._compute_pricelist_id()
        for order in self:
            if order.state and order.state != "draft":
                continue
            vals = order._sng_get_pricelist_rate_vals(order.pricelist_id)
            order.sng_use_custom_rate = vals["sng_use_custom_rate"]
            order.sng_custom_exchange_rate = vals["sng_custom_exchange_rate"]

    @api.onchange("pricelist_id", "company_id")
    def _onchange_sng_pricelist_custom_rate(self):
        for order in self:
            if order.state and order.state != "draft":
                continue
            vals = order._sng_get_pricelist_rate_vals(order.pricelist_id)
            order.sng_use_custom_rate = vals["sng_use_custom_rate"]
            order.sng_custom_exchange_rate = vals["sng_custom_exchange_rate"]

    @api.depends(
        "currency_id",
        "date_order",
        "company_id",
        "sng_use_custom_rate",
        "sng_custom_exchange_rate",
    )
    def _compute_currency_rate(self):
        super()._compute_currency_rate()
        for order in self:
            if order.sng_use_custom_rate and order.sng_custom_exchange_rate > 0:
                order.currency_rate = 1.0 / order.sng_custom_exchange_rate

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("pricelist_id") and "sng_use_custom_rate" not in vals:
                company = (
                    self.env["res.company"].browse(vals.get("company_id"))
                    if vals.get("company_id")
                    else self.env.company
                )
                pricelist = self.env["product.pricelist"].browse(vals["pricelist_id"])
                if (
                    pricelist.sng_use_custom_rate
                    and pricelist.sng_custom_exchange_rate > 0
                    and pricelist.sng_is_usd_currency
                    and pricelist.currency_id != company.currency_id
                ):
                    vals.update({
                        "sng_use_custom_rate": True,
                        "sng_custom_exchange_rate": pricelist.sng_custom_exchange_rate,
                    })
        orders = super().create(vals_list)
        for order in orders:
            if order.state == "draft" and order.pricelist_id and not order.sng_use_custom_rate:
                order.write(order._sng_get_pricelist_rate_vals(order.pricelist_id))
        return orders

    def write(self, vals):
        if "pricelist_id" in vals and "sng_use_custom_rate" not in vals:
            for order in self:
                order_vals = dict(vals)
                pricelist = (
                    self.env["product.pricelist"].browse(vals["pricelist_id"])
                    if vals["pricelist_id"]
                    else self.env["product.pricelist"]
                )
                if order.state == "draft":
                    order_vals.update(order._sng_get_pricelist_rate_vals(pricelist))
                super(SaleOrder, order).write(order_vals)
            return True
        return super().write(vals)

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.sng_use_custom_rate and self.sng_custom_exchange_rate > 0:
            invoice_vals.update({
                "sng_use_custom_rate": True,
                "sng_custom_exchange_rate": self.sng_custom_exchange_rate,
                "invoice_currency_rate": 1.0 / self.sng_custom_exchange_rate,
            })
        return invoice_vals


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_pricelist_price(self):
        self.ensure_one()
        if (
            self.order_id.sng_use_custom_rate
            and self.order_id.pricelist_id
            and self.order_id.pricelist_id.sng_use_custom_rate
            and self.order_id.pricelist_id.sng_is_usd_currency
        ):
            return self.order_id.pricelist_id._get_product_price(
                self.product_id.with_context(**self._get_product_price_context()),
                self.product_uom_qty or 1.0,
                uom=self.product_uom,
                date=self._get_order_date(),
                currency=self.currency_id,
            )
        return super()._get_pricelist_price()

    def _get_pricelist_price_before_discount(self):
        self.ensure_one()
        if (
            self.order_id.sng_use_custom_rate
            and self.order_id.pricelist_id
            and self.order_id.pricelist_id.sng_use_custom_rate
            and self.order_id.pricelist_id.sng_is_usd_currency
            and not self.pricelist_item_id
        ):
            return self._get_pricelist_price()
        return super()._get_pricelist_price_before_discount()
