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

    @api.depends("price_unit", "product_uom_qty")
    def _compute_subtotal(self):
        for move in self:
            move.subtotal = (move.price_unit or 0.0) * (move.product_uom_qty or 0.0)

    def _is_consignation_move(self):
        self.ensure_one()
        return bool(self.picking_id and self.picking_id.is_consignation_delivery)

    def _get_consignation_price_unit(self):
        self.ensure_one()
        product = self.product_id
        if not product:
            return 0.0

        product = product.with_company(self.company_id)
        partner = self.picking_id.partner_id if self.picking_id else None

        pricelist = partner.property_product_pricelist.with_company(self.company_id) if partner and partner.property_product_pricelist else None
        if pricelist:
            if hasattr(pricelist, "_get_product_price"):
                return pricelist._get_product_price(
                    product,
                    self.product_uom_qty or 1.0,
                    partner,
                    uom_id=self.product_uom,
                )
            if hasattr(pricelist, "_compute_price_rule"):
                res = pricelist._compute_price_rule(
                    [(product, self.product_uom_qty or 1.0, partner)],
                    date=False,
                    uom_id=self.product_uom,
                )
                if res.get(product.id):
                    return res[product.id][0]

        return product.lst_price or product.standard_price

    @api.onchange("product_id", "product_uom_qty", "product_uom", "picking_id", "picking_id.partner_id")
    def _onchange_set_consignation_price(self):
        for move in self:
            if not move.product_id:
                continue
            if not move._is_consignation_move():
                continue
            if move.price_unit:
                continue
            move.price_unit = move._get_consignation_price_unit()

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if move._is_consignation_move() and not move.price_unit and move.product_id:
                move.with_context(skip_consignation_price_check=True).price_unit = move._get_consignation_price_unit()
        return moves

    def write(self, vals):
        if (
            "price_unit" in vals
            and not self.env.context.get("skip_consignation_price_check")
            and not self.env.user.has_group(
                "sng_consignaciones_internas.group_consignation_delivery_price"
            )
        ):
            blocked = self.filtered(lambda m: m._is_consignation_move())
            if blocked:
                raise UserError(_("No tiene permisos para modificar precios en consignaciones."))
        return super().write(vals)
