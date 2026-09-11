# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    print_line_notes = fields.Boolean(
        string="Imprimir notas de línea",
        default=False,
        help="Si está marcado, se imprimen las notas de los productos en la "
             "cotización, el pedido y la factura proforma.",
    )
