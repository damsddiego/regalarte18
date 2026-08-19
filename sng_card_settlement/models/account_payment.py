# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    card_settlement_id = fields.Many2one(
        comodel_name="sng.card.settlement",
        string="Liquidación de tarjeta",
        copy=False,
        index=True,
        ondelete="set null",
    )
    is_card_settlement_required = fields.Boolean(
        string="Requiere liquidación de tarjeta",
        related="payment_method_line_id.is_card_settlement",
        store=True,
        readonly=True,
    )

    @api.depends(
        "move_id.line_ids.amount_residual",
        "move_id.line_ids.amount_residual_currency",
        "move_id.line_ids.account_id",
        "state",
        "is_card_settlement_required",
        "payment_type",
        "partner_type",
    )
    def _compute_reconciliation_status(self):
        super()._compute_reconciliation_status()
        for payment in self:
            if (
                payment.is_card_settlement_required
                and payment.payment_type == "inbound"
                and payment.partner_type == "customer"
                and payment.state in ("in_process", "paid")
                and payment.move_id
            ):
                # For card settlements, the invoice must become fully paid as soon as the
                # payment is applied to the receivable. The bank settlement is tracked later
                # through the outstanding account and the daily settlement entry.
                payment.is_matched = payment.is_reconciled

    def action_open_card_settlement(self):
        self.ensure_one()
        if not self.card_settlement_id:
            raise UserError(_("Este pago no tiene una liquidación de tarjeta asociada."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Liquidación de tarjeta"),
            "res_model": "sng.card.settlement",
            "view_mode": "form",
            "res_id": self.card_settlement_id.id,
            "target": "current",
        }
