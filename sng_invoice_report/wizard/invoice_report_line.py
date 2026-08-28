from odoo import fields, models


class InvoiceReportLine(models.TransientModel):
    _name = 'invoice.report.line'
    _description = 'Invoice Report Line'
    _order = 'salesperson_id, invoice_date, move_id, id'

    wizard_id = fields.Many2one(
        'invoice.report.wizard',
        required=True,
        ondelete='cascade',
        index=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Invoice',
        required=True,
        readonly=True,
        index=True,
    )
    invoice_date = fields.Date(string='Date', readonly=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        readonly=True,
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        string='Company Currency',
        required=True,
        readonly=True,
    )
    invoice_user_id = fields.Many2one(
        'res.users',
        string='Invoice Responsible',
        readonly=True,
    )
    original_salesperson_id = fields.Many2one(
        'res.partner',
        string='Original Salesperson',
        readonly=True,
    )
    salesperson_id = fields.Many2one(
        'res.partner',
        string='Report Salesperson',
        readonly=True,
        index=True,
    )
    move_type = fields.Char(string='Type', readonly=True)
    payment_state = fields.Char(string='Payment Status', readonly=True)
    amount_untaxed = fields.Monetary(
        string='Untaxed',
        currency_field='currency_id',
        readonly=True,
    )
    amount_tax = fields.Monetary(
        string='Tax',
        currency_field='currency_id',
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        readonly=True,
    )
    amount_untaxed_company = fields.Monetary(
        string='Subtotal (Company Currency)',
        currency_field='company_currency_id',
        readonly=True,
    )
    amount_tax_company = fields.Monetary(
        string='Tax (Company Currency)',
        currency_field='company_currency_id',
        readonly=True,
    )
    amount_total_company = fields.Monetary(
        string='Total (Company Currency)',
        currency_field='company_currency_id',
        readonly=True,
    )

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
