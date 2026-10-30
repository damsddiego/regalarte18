# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    fe_xml_line = fields.Boolean(
        string="Línea importada del XML",
        readonly=True,
        copy=False,
        help="Técnico: la línea se creó a partir del XML de factura electrónica del proveedor.",
    )

    def _sng_keep_xml_amounts(self):
        """True si la línea viene del XML y el proveedor pide conservar sus montos."""
        self.ensure_one()
        move = self.move_id
        return bool(
            self.fe_xml_line
            and move.move_type in ("in_invoice", "in_refund")
            and move.partner_id.commercial_partner_id.fe_keep_xml_line_amounts
        )

    @api.depends("product_id", "product_uom_id")
    def _compute_price_unit(self):
        keep = self.filtered(lambda line: line._sng_keep_xml_amounts())
        super(AccountMoveLine, self - keep)._compute_price_unit()

    @api.depends("product_id", "product_uom_id")
    def _compute_tax_ids(self):
        keep = self.filtered(lambda line: line._sng_keep_xml_amounts())
        super(AccountMoveLine, self - keep)._compute_tax_ids()
