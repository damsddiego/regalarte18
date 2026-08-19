# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = "account.payment.method.line"

    is_card_settlement = fields.Boolean(
        string="Liquidación de tarjeta",
        help="Si está activo, los pagos creados con este método podrán agruparse en una "
             "liquidación diaria de tarjeta.",
    )
