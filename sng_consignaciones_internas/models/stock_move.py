# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    subtotal = fields.Monetary(
        string="Subtotal",
        compute="_compute_subtotal",
        store=True,
        currency_field="currency_id",
    )
    currency_usd_id = fields.Many2one(
        "res.currency",
        compute="_compute_usd_amounts",
        readonly=True,
    )
    price_unit_usd = fields.Monetary(
        string="Precio unitario USD",
        compute="_compute_usd_amounts",
        currency_field="currency_usd_id",
        readonly=True,
    )
    subtotal_usd = fields.Monetary(
        string="Subtotal USD",
        compute="_compute_usd_amounts",
        currency_field="currency_usd_id",
        readonly=True,
    )

    @api.depends("price_unit", "product_uom_qty")
    def _compute_subtotal(self):
        for move in self:
            move.subtotal = (move.price_unit or 0.0) * (move.product_uom_qty or 0.0)

    @api.depends(
        "price_unit",
        "product_uom_qty",
        "quantity",
        "picking_id",
        "picking_id.partner_id",
        "picking_id.date_done",
        "picking_id.scheduled_date",
        "picking_id.is_consignation_usd",
    )
    def _compute_usd_amounts(self):
        for move in self:
            picking = move.picking_id
            if not picking or not picking.is_consignation_usd:
                move.currency_usd_id = False
                move.price_unit_usd = 0.0
                move.subtotal_usd = 0.0
                continue

            currency, pricelist = picking._get_consignation_report_currency()
            quantity = picking._get_consignation_report_qty(move) or 0.0
            price_unit = move.price_unit or 0.0
            move.currency_usd_id = currency
            move.price_unit_usd = picking._convert_consignation_report_amount(
                price_unit, currency, pricelist,
            )
            move.subtotal_usd = picking._convert_consignation_report_amount(
                price_unit * quantity, currency, pricelist,
            )

    def _uses_transfer_prices(self):
        self.ensure_one()
        return bool(self.picking_id and self.picking_id.use_transfer_prices)

    def _get_transfer_price_unit(self):
        self.ensure_one()
        product = self.product_id
        if not product:
            return 0.0

        product = product.with_company(self.company_id)
        partner = self.picking_id.partner_id if self.picking_id else None

        pricelist = partner.property_product_pricelist.with_company(self.company_id) if partner and partner.property_product_pricelist else None
        if pricelist:
            try:
                price = pricelist._get_product_price(
                    product,
                    self.product_uom_qty or 1.0,
                    currency=pricelist.currency_id,
                    uom=self.product_uom,
                    date=self.picking_id.scheduled_date or fields.Datetime.now(),
                )
                company_currency = self.company_id.currency_id
                if pricelist.currency_id == company_currency:
                    return price

                custom_rate = getattr(pricelist, "sng_custom_exchange_rate", 0.0) or 0.0
                if pricelist.currency_id.name == "USD" and custom_rate > 0:
                    return price * custom_rate

                return pricelist.currency_id._convert(
                    price,
                    company_currency,
                    self.company_id,
                    fields.Date.to_date(self.picking_id.scheduled_date)
                    or fields.Date.context_today(self),
                    round=False,
                )
            except (TypeError, ZeroDivisionError):
                # Currency conversion failed (missing exchange rate)
                pass

        return product.lst_price or product.standard_price

    @api.onchange("product_id", "product_uom_qty", "product_uom", "picking_id", "picking_id.partner_id")
    def _onchange_set_consignation_price(self):
        for move in self:
            if not move.product_id:
                continue
            if not move._uses_transfer_prices():
                continue
            if move.price_unit:
                continue
            move.price_unit = move._get_transfer_price_unit()

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if move._uses_transfer_prices() and not move.price_unit and move.product_id:
                move.with_context(skip_transfer_price_check=True).price_unit = move._get_transfer_price_unit()
        return moves

    def write(self, vals):
        if (
            "price_unit" in vals
            and not self.env.context.get("skip_transfer_price_check")
            and not self.env.context.get("skip_consignation_price_check")
            and not self.env.user.has_group(
                "sng_consignaciones_internas.group_consignation_delivery_price"
            )
        ):
            blocked = self.filtered(lambda m: m._uses_transfer_prices())
            if blocked:
                raise UserError(_("No tiene permisos para modificar precios en traslados."))
        return super().write(vals)

    def _get_price_unit(self):
        """El precio de transferencia de consignación es informativo (se muestra en el
        picking y en los reportes); la valoración de inventario debe usar el costo del
        producto. Sin esto, las entradas sin compra (retornos RETC, recepciones de
        consignatarios, rellenos) se valoran al precio de venta e inflan el costo
        promedio (caso Peluche Perezoso Roxy 113003040, 2026-08)."""
        self.ensure_one()
        if (
            self._uses_transfer_prices()
            and not getattr(self, "purchase_line_id", False)
            and not self.origin_returned_move_id
            and self.price_unit
        ):
            if self.product_id.lot_valuated:
                return {
                    lot: lot.standard_price
                    or self.product_id.with_company(self.company_id).standard_price
                    for lot in self.lot_ids
                }
            return {
                self.env["stock.lot"]: self.product_id.with_company(
                    self.company_id
                ).standard_price
            }
        return super()._get_price_unit()
