from odoo import models, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('product_id', 'partner_id', 'move_id.partner_id')
    def _compute_account_id(self):
        """Override to use partner's expense account when available for vendor bills."""
        super()._compute_account_id()
        for line in self:
            # Only apply for vendor bills (in_invoice, in_refund)
            if line.move_id.move_type in ('in_invoice', 'in_refund'):
                partner = line.move_id.partner_id
                # Check if partner has an expense account assigned
                if partner and partner.expense_account_id:
                    # Only apply to product lines, not payment terms or tax lines
                    # Exclude payable/receivable accounts (payment term lines)
                    if (line.display_type == 'product' and
                        line.account_id and
                        line.account_id.account_type not in ('liability_payable', 'asset_receivable')):
                        line.account_id = partner.expense_account_id
