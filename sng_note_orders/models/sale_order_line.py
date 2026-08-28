# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    sng_line_note = fields.Text(string="Nota")
