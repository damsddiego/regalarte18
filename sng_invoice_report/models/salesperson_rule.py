from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InvoiceReportSalespersonRule(models.Model):
    _name = 'invoice.report.salesperson.rule'
    _description = 'Invoice Report Salesperson Rule'
    _order = 'company_id, user_id, id'

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Invoice Responsible',
        required=True,
        index=True,
        domain=[('share', '=', False)],
        help="Invoices whose responsible user matches this user are reassigned in this report.",
    )
    salesperson_id = fields.Many2one(
        'res.partner',
        string='Report Salesperson',
        required=True,
        index=True,
        domain=[('is_salesperson', '=', True)],
        help="Salesperson shown by the invoice report for matching invoices.",
    )

    _sql_constraints = [
        (
            'user_company_unique',
            'unique(user_id, company_id)',
            'Only one invoice report salesperson rule is allowed per user and company.',
        ),
    ]

    @api.constrains('salesperson_id')
    def _check_salesperson(self):
        for rule in self:
            if rule.salesperson_id and not rule.salesperson_id.is_salesperson:
                raise ValidationError(
                    _("The report salesperson must be marked as a salesperson.")
                )
