# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    outstanding_move_lines = fields.One2many('outstanding.account.move', 'pyament_id', string="Moves")
    pay_moves = fields.Boolean('Pay Moves', copy=0)
    writeoff_amt = fields.Float(string='Writeoff Amount')
    writeoff_account_id = fields.Many2one(comodel_name='account.account', string="Writeoff Account", copy=False, domain="[('deprecated', '=', False)]", 
        check_company=True)
    writeoff_notes = fields.Char('Writeoff Notes')

    def _load_outstanding_moves(self):
        """Populate outstanding_move_lines with open documents for the partner."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Please select a partner before loading documents."))
        if not self.currency_id:
            raise UserError(_("Please select a currency before loading documents."))
        move_type = ['out_invoice'] if self.payment_type == 'inbound' else ['in_invoice']
        moves = self.env["account.move"].search([
            ('state', '=', 'posted'),
            ('partner_id', '=', self.partner_id.id),
            ('move_type', 'in', move_type),
            ('amount_residual', '!=', 0),
            ('currency_id', '=', self.currency_id.id),
        ], order='invoice_date')
        if not moves:
            raise UserError(_("No posted invoices/bills with a residual amount were found for this partner."))

        move_lines = [(5, 0, 0)]  # clear existing lines
        for move in moves:
            move_lines.append((0, 0, {
                'name': move.name,
                'account_move_id': move.id,
            }))
        # reset write-off suggestion but keep original payment amount (comes from external app)
        self.writeoff_amt = 0
        self.outstanding_move_lines = move_lines

    def action_reload_outstanding_moves(self):
        """Button to reload outstanding invoices/bills while in draft."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("You can reload outstanding documents only in draft payments."))
        self.pay_moves = True
        self._load_outstanding_moves()
        return True

    #change lines selection then set 'Retencion Amount' as 0 and also change 'Amount' of payment
    @api.onchange('pay_moves', 'outstanding_move_lines')
    def _onchange_outstanding_move_lines(self):
        """When selecting invoices/bills to pay, keep the original payment amount
        (imported from external app) and only suggest/update the write-off amount
        as the difference between selected invoices and the fixed payment amount.
        """
        if self.pay_moves and self.outstanding_move_lines:
            outstanding_move_ids = self.outstanding_move_lines.filtered(lambda pl: pl.select_to_pay)
            if outstanding_move_ids and self.amount:
                total_invoice_amount = sum(outstanding_move_ids.mapped('amount_residual'))
                # Suggest write-off as positive difference (if any)
                self.writeoff_amt = max(0.0, total_invoice_amount - self.amount)
            else:
                self.writeoff_amt = 0.0

    #change 'Write-Off Amount' then change 'Amount' of payment and also manage warning based on Amount
    @api.onchange('writeoff_amt')
    def _onchange_line_writeoff_amounts(self):
        """Do not change the original payment amount when user edits write-off.
        Only validate the coherence between:
            sum(selected invoices)  vs  payment amount + write-off amount.
        """
        if self.pay_moves and self.outstanding_move_lines:
            outstanding_move_ids = self.outstanding_move_lines.filtered(lambda pl: pl.select_to_pay)
            if outstanding_move_ids:
                total_invoice_amount = sum(outstanding_move_ids.mapped('amount_residual'))
                payment_amount = self.amount or 0.0
                writeoff_amount = self.writeoff_amt or 0.0

                # If no write-off is set, allow difference so that remaining amount
                # stays as credit in favor of the customer/vendor.
                if writeoff_amount <= 0:
                    return

                # If a positive write-off is set, enforce strict equality.
                total_payment_and_writeoff = payment_amount + writeoff_amount
                if self.currency_id.compare_amounts(total_payment_and_writeoff, total_invoice_amount) != 0:
                    return {
                        'warning': {
                            'title': "Warning!",
                            'message': (
                                "The total of the selected invoices ({:.2f}) is not equal to "
                                "Payment amount ({:.2f}) + Write-off amount ({:.2f}) = {:.2f}."
                            ).format(
                                total_invoice_amount,
                                payment_amount,
                                writeoff_amount,
                                total_payment_and_writeoff,
                            ),
                        }
                    }

    @api.onchange('partner_id')
    def _onchange_partner(self):
        if not self.partner_id:
            self.pay_moves = False
    
    @api.onchange('pay_moves')
    def _onchange_pay_moves(self):
        if self.pay_moves:
            self._load_outstanding_moves()

    def _get_selected_outstanding_moves(self):
        self.ensure_one()
        return self.outstanding_move_lines.filtered(lambda line: line.select_to_pay)

    def _prepare_payment_writeoff_line_vals(self):
        self.ensure_one()
        if (
            not self.pay_moves
            or not self._get_selected_outstanding_moves()
            or not self.writeoff_account_id
            or self.currency_id.is_zero(self.writeoff_amt or 0.0)
        ):
            return []

        amount_currency = abs(self.writeoff_amt)
        if self.payment_type == 'outbound':
            amount_currency = -amount_currency
        balance = self.currency_id._convert(
            amount_currency,
            self.company_id.currency_id,
            self.company_id,
            self.date,
        )
        return [{
            'name': 'Write-Off',
            'account_id': self.writeoff_account_id.id,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'amount_currency': amount_currency,
            'balance': balance,
            'debit': balance if balance > 0.0 else 0.0,
            'credit': -balance if balance < 0.0 else 0.0,
            'writeoff_notes': self.writeoff_notes or '',
        }]

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        if write_off_line_vals is None:
            write_off_line_vals = self._prepare_payment_writeoff_line_vals()
        return super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
        )

    def _validate_pay_moves_configuration(self):
        for payment in self.filtered(lambda pay: pay.pay_moves):
            selected_lines = payment._get_selected_outstanding_moves()
            writeoff_amount = payment.writeoff_amt or 0.0
            if writeoff_amount < 0:
                raise UserError(_("The write-off amount cannot be negative."))
            if payment.currency_id.is_zero(writeoff_amount):
                continue
            if not selected_lines:
                raise UserError(_("Select at least one invoice/bill before using a write-off."))
            if not payment.writeoff_account_id:
                raise UserError(_("Select a write-off account before posting this payment."))

            selected_total = sum(selected_lines.mapped('amount_residual'))
            total_payment_and_writeoff = (payment.amount or 0.0) + writeoff_amount
            if payment.currency_id.compare_amounts(total_payment_and_writeoff, selected_total) != 0:
                doc_type = _('invoices') if payment.payment_type == 'inbound' else _('bills')
                raise UserError(_(
                    "Payment mismatch!\n\n"
                    "The total of the selected %(doc_type)s is %(selected_total).2f, but "
                    "payment amount %(payment_amount).2f + write-off amount %(writeoff_amount).2f "
                    "is %(total).2f."
                ) % {
                    'doc_type': doc_type,
                    'selected_total': selected_total,
                    'payment_amount': payment.amount,
                    'writeoff_amount': writeoff_amount,
                    'total': total_payment_and_writeoff,
                })

    def action_validate(self):
        for payment in self.filtered(lambda pay: pay.pay_moves):
            selected_lines = payment._get_selected_outstanding_moves()
            if not selected_lines:
                continue

            counterpart_line = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.destination_account_id and not line.reconciled
            )
            if len(counterpart_line) != 1:
                raise UserError(_(
                    "The payment %(payment)s does not have a single open receivable/payable line to reconcile."
                ) % {'payment': payment.display_name})

            for outstanding_line in selected_lines:
                if counterpart_line.reconciled:
                    break
                invoice = outstanding_line.account_move_id
                invoice_lines = invoice.line_ids.filtered(
                    lambda line: line.account_id == counterpart_line.account_id and not line.reconciled
                )
                if not invoice_lines:
                    continue
                invoice.js_assign_outstanding_line(counterpart_line.id)
                counterpart_line.invalidate_recordset([
                    'amount_residual',
                    'amount_residual_currency',
                    'reconciled',
                    'matched_debit_ids',
                    'matched_credit_ids',
                ])
        return super().action_validate()

    def action_draft(self):
        res = super().action_draft()
        for payment in self.filtered(lambda pay: pay.move_id and pay.pay_moves):
            payment.move_id.unlink()
        return res 

    def action_post(self):
        self._validate_pay_moves_configuration()
        res = super().action_post()
        payments_to_validate = self.filtered(lambda pay: pay.pay_moves)
        if payments_to_validate:
            payments_to_validate.action_validate()
        return res

    def unlink(self):
        for rec in self:
            rec.outstanding_move_lines.unlink()
        return super(AccountPayment, self).unlink()

class OutStandingAccountMove(models.Model):
    _name = 'outstanding.account.move'
    _description = 'Outstanding Account Moves'

    pyament_id = fields.Many2one('account.payment', string='Payment', required=True)#O2M
    select_to_pay = fields.Boolean('Select', copy=0)
    name = fields.Char(string="Number")
    account_move_id = fields.Many2one('account.move', string='Move', required=True)
    move_currency_id = fields.Many2one(string='Move Currency', related='account_move_id.currency_id', readonly=True)
    invoice_date = fields.Date(string="Date",related='account_move_id.invoice_date')
    ref = fields.Char(string="Reference", related='account_move_id.ref', readonly=True)
    company_id = fields.Many2one('res.company', string='Company',related='account_move_id.company_id',)
    company_currency_id = fields.Many2one(string='Company Currency', related='company_id.currency_id', readonly=True)
    amount_untaxed = fields.Monetary( 
        string='Untaxed Amount',
        related='account_move_id.amount_untaxed', readonly=True,
        currency_field='move_currency_id')
    amount_total = fields.Monetary(
        string='Total Amount',
        related='account_move_id.amount_total', readonly=True,
        currency_field='move_currency_id',
    )
    amount_residual = fields.Monetary(
        string='Amount Due',
        related='account_move_id.amount_residual', readonly=True,
        currency_field='move_currency_id'
    )
    
    def open_invoice(self):
        self.ensure_one()
        name = ''
        if self.account_move_id.move_type == 'out_invoice':
            name = 'Customer Invoice'
        if self.account_move_id.move_type == 'in_invoice':
            name = 'Vendor Bill'
        return {
            'type': 'ir.actions.act_window',
            #'name': _("Customer Invoice"),
            'name': name,
            'view_id': self.env.ref('account.view_move_form').id,
            'context': self.env.context,
            'res_model': 'account.move',
            'res_id': self.account_move_id.id,
            'target': 'new',
            'view_mode': 'form',
        }
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
