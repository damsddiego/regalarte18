# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    consolidated_payment_id = fields.Many2one(
        comodel_name="consolidated.customer.payment",
        string="Pago consolidado",
        copy=False,
        index=True,
        ondelete="set null",
    )

    def action_open_consolidated_payment(self):
        self.ensure_one()
        if not self.consolidated_payment_id:
            raise UserError(_("Este pago no fue generado por un pago consolidado."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Pago consolidado"),
            "res_model": "consolidated.customer.payment",
            "view_mode": "form",
            "target": "current",
            "res_id": self.consolidated_payment_id.id,
        }
