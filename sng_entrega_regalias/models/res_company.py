# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    regalia_expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta de gasto de regalías",
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help="Cuenta que se debita con el costo de los productos regalados.",
    )
    regalia_counterpart_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta contrapartida de regalías",
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help="Cuenta de inventario/contrapartida que se acredita al entregar regalías.",
    )
    regalia_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de regalías",
        domain="[('type', '=', 'general'), ('company_id', '=', id)]",
        check_company=True,
        help="Diario misceláneo donde se registran los asientos de regalías. "
             "Si no se define, se usa el primer diario misceláneo de la compañía.",
    )
