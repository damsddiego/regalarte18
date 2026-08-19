# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    _redirect_partner_once_param = (
        "sng_consignaciones_internas.redirect_partner_872_to_3920_once"
    )

    use_transfer_prices = fields.Boolean(
        compute="_compute_use_transfer_prices",
        store=True,
    )

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
        help="Total informativo del traslado.",
    )
    is_consignation_delivery = fields.Boolean(
        compute="_compute_is_consignation_delivery",
        store=True,
    )
    is_consignation_usd = fields.Boolean(
        compute="_compute_is_consignation_usd",
    )
    print_line_notes = fields.Boolean(
        string="Imprimir notas de línea",
        default=False,
        help="Si está marcado, se imprimen las notas de línea en la entrega de consignación.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        config = self.env["ir.config_parameter"].sudo()
        redirect_enabled = config.get_param(self._redirect_partner_once_param) == "1"
        redirected = False
        normalized_vals_list = []

        for vals in vals_list:
            vals = dict(vals)
            if (
                redirect_enabled
                and not redirected
                and vals.get("partner_id") == 872
                and self._should_redirect_consignation_partner(vals)
            ):
                vals["partner_id"] = 3920
                redirected = True
            normalized_vals_list.append(vals)

        records = super().create(normalized_vals_list)
        if redirected:
            config.set_param(self._redirect_partner_once_param, "0")
        return records

    def _should_redirect_consignation_partner(self, vals):
        picking_type_id = vals.get("picking_type_id")
        if not picking_type_id:
            return False
        picking_type = self.env["stock.picking.type"].browse(picking_type_id).exists()
        return bool(
            picking_type
            and picking_type.code == "internal"
            and picking_type.sequence_code == "CONS"
        )

    @api.depends("picking_type_id", "picking_type_id.code")
    def _compute_use_transfer_prices(self):
        for picking in self:
            picking.use_transfer_prices = bool(
                picking.picking_type_id
                and picking.picking_type_id.code in ("internal", "incoming", "outgoing")
            )

    @api.depends("picking_type_id", "picking_type_id.code", "picking_type_id.sequence_code")
    def _compute_is_consignation_delivery(self):
        for picking in self:
            picking.is_consignation_delivery = bool(
                picking.picking_type_id
                and picking.picking_type_id.code == "internal"
                and picking.picking_type_id.sequence_code == "CONS"
            )

    @api.depends("is_consignation_delivery", "partner_id", "company_id")
    def _compute_is_consignation_usd(self):
        for picking in self:
            if not picking.is_consignation_delivery:
                picking.is_consignation_usd = False
                continue
            currency, _pricelist = picking._get_consignation_report_currency()
            picking.is_consignation_usd = currency.name == "USD"

    @api.depends("move_ids_without_package.subtotal")
    def _compute_amount_total(self):
        for picking in self:
            picking.amount_total = sum(picking.move_ids_without_package.mapped("subtotal"))

    def _get_consignation_report_qty(self, move):
        self.ensure_one()
        return move.quantity if self.state == "done" else move.product_uom_qty

    def _get_consignation_report_taxes(self, move):
        self.ensure_one()
        product = move.product_id
        taxes = product.taxes_id.filtered(
            lambda tax: not tax.company_id or tax.company_id == self.company_id
        )
        partner = self.partner_id or move.partner_id
        fiscal_position = partner.property_account_position_id if partner else False
        if fiscal_position:
            taxes = fiscal_position.map_tax(taxes)
        return taxes

    def _get_consignation_report_currency(self):
        """Return the currency in which the consignment delivery is printed.

        Transfer prices are stored in the company currency.  A consignee with
        a USD pricelist, however, must receive the delivery note in USD.
        """
        self.ensure_one()
        partner = self.partner_id or (
            self.move_ids_without_package
            and self.move_ids_without_package[0].partner_id
        )
        pricelist = (
            partner.with_company(self.company_id).property_product_pricelist
            if partner else self.env["product.pricelist"]
        )
        if pricelist and pricelist.currency_id.name == "USD":
            return pricelist.currency_id, pricelist
        return self.company_id.currency_id, pricelist

    def _convert_consignation_report_amount(self, amount, currency, pricelist):
        """Convert a company-currency amount for the consignment PDF.

        A positive ``sng_custom_exchange_rate`` takes precedence.  Its value
        is expressed as company currency per USD; otherwise Odoo's configured
        currency rate at the transfer date is used.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if currency == company_currency:
            return amount

        custom_rate = getattr(pricelist, "sng_custom_exchange_rate", 0.0) or 0.0
        if currency.name == "USD" and custom_rate > 0:
            return amount / custom_rate

        conversion_date = fields.Date.to_date(self.date_done or self.scheduled_date)
        return company_currency._convert(
            amount,
            currency,
            self.company_id,
            conversion_date or fields.Date.context_today(self),
            round=False,
        )

    def _get_consignation_report_lines(self):
        self.ensure_one()
        lines = []
        company_currency = self.company_id.currency_id
        currency, pricelist = self._get_consignation_report_currency()
        partner = self.partner_id or (
            self.move_ids_without_package
            and self.move_ids_without_package[0].partner_id
        )
        for move in self.move_ids_without_package:
            quantity = self._get_consignation_report_qty(move) or 0.0
            price_unit = move.price_unit or 0.0
            taxes = self._get_consignation_report_taxes(move)
            tax_result = taxes.compute_all(
                price_unit,
                currency=company_currency,
                quantity=quantity,
                product=move.product_id,
                partner=partner,
            )
            lines.append({
                "code": move.product_id.default_code or "",
                "product": move.description_picking or move.product_id.name or "",
                "sng_line_note": (
                    move.sng_line_note.strip()
                    if "sng_line_note" in move._fields and move.sng_line_note
                    else ""
                ),
                "quantity": quantity,
                "price_unit": self._convert_consignation_report_amount(
                    price_unit, currency, pricelist,
                ),
                "subtotal": self._convert_consignation_report_amount(
                    tax_result["total_excluded"], currency, pricelist,
                ),
                "tax": self._convert_consignation_report_amount(
                    tax_result["total_included"] - tax_result["total_excluded"],
                    currency,
                    pricelist,
                ),
                "total": self._convert_consignation_report_amount(
                    tax_result["total_included"], currency, pricelist,
                ),
            })
        return lines

    def _get_consignation_report_totals(self):
        self.ensure_one()
        lines = self._get_consignation_report_lines()
        return {
            "quantity": sum(line["quantity"] for line in lines),
            "subtotal": sum(line["subtotal"] for line in lines),
            "tax": sum(line["tax"] for line in lines),
            "total": sum(line["total"] for line in lines),
        }

    def _get_consignation_report_values(self):
        self.ensure_one()
        lines = self._get_consignation_report_lines()
        currency, _pricelist = self._get_consignation_report_currency()
        return {
            "lines": lines,
            "currency": currency,
            "totals": {
                "quantity": sum(line["quantity"] for line in lines),
                "subtotal": sum(line["subtotal"] for line in lines),
                "tax": sum(line["tax"] for line in lines),
                "total": sum(line["total"] for line in lines),
            },
        }
