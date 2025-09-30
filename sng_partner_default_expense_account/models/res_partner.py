# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"

    property_expense_account_id = fields.Many2one(
        "account.account",
        string="Cuenta de gasto por defecto",
        company_dependent=True,
        #El dominio lo movi a la vista
        #domain="[('account_type', '=', 'expense'), ('company_id', '=', company_id)]",
        help=(
            "Si se define, Odoo usará esta cuenta por defecto en líneas de factura "
            "de proveedor que no tengan producto ni cuenta seleccionada."
        ),
    )
