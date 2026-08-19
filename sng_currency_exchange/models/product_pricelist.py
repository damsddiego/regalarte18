# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    sng_use_custom_rate = fields.Boolean(
        string="Usar Tipo de Cambio Fijo",
        default=False,
        help="Si está marcado, esta lista usa un tipo de cambio fijo para convertir precios desde la moneda de la compañía.",
    )
    sng_custom_exchange_rate = fields.Float(
        string="Tipo de Cambio Fijo",
        digits=(16, 6),
        default=0.0,
        help="Tipo de cambio expresado en moneda de la compañía por 1 unidad de moneda extranjera (ej: 520 CRC por USD).",
    )
    sng_is_usd_currency = fields.Boolean(
        string="Es USD",
        compute="_compute_sng_is_usd_currency",
    )

    @api.depends("currency_id")
    def _compute_sng_is_usd_currency(self):
        for pricelist in self:
            pricelist.sng_is_usd_currency = pricelist.currency_id.name == "USD"

    @api.constrains("sng_use_custom_rate", "sng_custom_exchange_rate", "currency_id", "company_id")
    def _check_sng_custom_rate(self):
        for pricelist in self:
            if not pricelist.sng_use_custom_rate:
                continue
            if not pricelist.sng_is_usd_currency:
                raise ValidationError(_("El tipo de cambio fijo solo puede activarse en listas de precio USD."))
            if pricelist.sng_custom_exchange_rate <= 0:
                raise ValidationError(_("El tipo de cambio fijo debe ser mayor que cero."))
            company = pricelist.company_id or self.env.company
            if pricelist.currency_id == company.currency_id:
                raise ValidationError(_(
                    "El tipo de cambio fijo solo aplica cuando la moneda de la lista es distinta "
                    "a la moneda de la compañía."
                ))

    def _sng_convert_with_custom_rate(self, amount, src_currency, target_currency):
        self.ensure_one()
        if (
            self.sng_use_custom_rate
            and self.sng_custom_exchange_rate > 0
            and self.sng_is_usd_currency
            and self.currency_id == target_currency
        ):
            company = self.company_id or self.env.company
            if src_currency == company.currency_id and target_currency != company.currency_id:
                return amount / self.sng_custom_exchange_rate
            if src_currency != company.currency_id and target_currency == company.currency_id:
                return amount * self.sng_custom_exchange_rate
        return False

    def _compute_price_rule(
            self, products, quantity, currency=None, uom=None, date=False, compute_price=True,
            **kwargs
    ):
        results = super()._compute_price_rule(
            products, quantity, currency=currency, uom=uom, date=date,
            compute_price=compute_price, **kwargs
        )
        if not compute_price or not self or not self.sng_use_custom_rate:
            return results

        target_currency = currency or self.currency_id or self.env.company.currency_id
        company = self.company_id or self.env.company
        if target_currency != self.currency_id or self.currency_id == company.currency_id:
            return results

        for product in products:
            price, rule_id = results.get(product.id, (0.0, False))
            if rule_id:
                continue
            product_uom = product.uom_id
            target_uom = uom or product_uom
            base_price = product._price_compute("list_price", uom=target_uom, date=date)[product.id]
            converted_price = self._sng_convert_with_custom_rate(
                base_price, product.currency_id, target_currency
            )
            if converted_price is not False:
                results[product.id] = (converted_price, rule_id)
            else:
                results[product.id] = (price, rule_id)
        return results


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    def _compute_base_price(self, product, quantity, uom, date, currency):
        price = super()._compute_base_price(product, quantity, uom, date, currency)
        if not self.pricelist_id.sng_use_custom_rate:
            return price

        rule_base = self.base or "list_price"
        if rule_base == "pricelist" and self.base_pricelist_id:
            src_currency = self.base_pricelist_id.currency_id
        elif rule_base == "standard_price":
            src_currency = product.cost_currency_id
        else:
            src_currency = product.currency_id

        if rule_base == "pricelist":
            base_price = self.base_pricelist_id._get_product_price(
                product, quantity, currency=self.base_pricelist_id.currency_id, uom=uom, date=date
            )
        else:
            base_price = product._price_compute(rule_base, uom=uom, date=date)[product.id]

        custom_price = self.pricelist_id._sng_convert_with_custom_rate(
            base_price, src_currency, currency
        )
        return custom_price if custom_price is not False else price
