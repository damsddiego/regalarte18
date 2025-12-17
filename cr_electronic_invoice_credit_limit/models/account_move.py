from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Add a computed field to track credit note totals
    credit_note_total = fields.Monetary(
        string='Total Credit Notes',
        compute='_compute_credit_note_total',
        store=True,
        help='Total amount of credit notes created for this invoice'
    )

    @api.depends('reversed_entry_id', 'reversed_entry_id.line_ids', 'state')
    def _compute_credit_note_total(self):
        """Compute the total amount of credit notes for an invoice"""
        for move in self:
            if move.move_type == 'out_refund' and move.reversed_entry_id:
                # Find all credit notes linked to the original invoice
                credit_notes = self.env['account.move'].search([
                    ('reversed_entry_id', '=', move.reversed_entry_id.id),
                    ('state', 'not in', ['cancel', 'draft']),
                    ('move_type', '=', 'out_refund')
                ])
                move.credit_note_total = sum(credit_notes.mapped('amount_total'))
            else:
                move.credit_note_total = 0.0

    @api.constrains('move_type', 'reversed_entry_id', 'amount_total', 'state')
    def _check_credit_note_limit(self):
        """Ensure credit note total doesn't exceed original invoice amount"""
        for move in self:
            # Only check for out_refund (credit notes) that are linked to an original invoice
            # and are not in cancel state
            if (move.move_type == 'out_refund' and move.reversed_entry_id and 
                move.state not in ['cancel', 'draft']):
                original_invoice = move.reversed_entry_id
                # Skip the check if original invoice is cancelled
                if original_invoice.state == 'cancel':
                    continue
                    
                # Calculate total of all credit notes including this one
                # Exclude draft and cancelled credit notes
                existing_credit_notes = self.env['account.move'].search([
                    ('reversed_entry_id', '=', original_invoice.id),
                    ('state', 'not in', ['cancel', 'draft']),
                    ('move_type', '=', 'out_refund'),
                    ('id', '!=', move.id)
                ])
                total_credit_amount = sum(existing_credit_notes.mapped('amount_total')) + move.amount_total
                
                # Allow a small tolerance for rounding differences
                if total_credit_amount > (original_invoice.amount_total + 0.01):
                    raise ValidationError(_(
                        "The total amount of credit notes (%.2f) cannot exceed "
                        "the original invoice amount (%.2f).\n"
                        "Original Invoice: %s\n"
                        "Current Credit Notes Total: %.2f\n"
                        "This Credit Note Amount: %.2f"
                    ) % (
                        total_credit_amount,
                        original_invoice.amount_total,
                        original_invoice.name,
                        sum(existing_credit_notes.mapped('amount_total')),
                        move.amount_total
                    ))