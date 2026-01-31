# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    amount_total = fields.Monetary(
        string="Total",
        compute="_compute_amount_total",
        store=True,
        currency_field="currency_id",
        help="Total informativo del traslado en consignación.",
    )
    is_consignation_delivery = fields.Boolean(
        compute="_compute_is_consignation_delivery",
        store=True,
    )

    @api.depends("picking_type_id", "picking_type_id.code", "picking_type_id.sequence_code")
    def _compute_is_consignation_delivery(self):
        for picking in self:
            picking.is_consignation_delivery = bool(
                picking.picking_type_id
                and picking.picking_type_id.code == "internal"
                and picking.picking_type_id.sequence_code == "CONS"
            )

    @api.depends("move_ids_without_package.subtotal")
    def _compute_amount_total(self):
        for picking in self:
            picking.amount_total = sum(picking.move_ids_without_package.mapped("subtotal"))
