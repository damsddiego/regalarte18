from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta de Gasto',
        domain="[('account_type', 'in', ['expense', 'expense_direct_cost', 'expense_depreciation'])]",
        company_dependent=True,
        help='Cuenta contable de gasto asignada a este cliente',
    )
