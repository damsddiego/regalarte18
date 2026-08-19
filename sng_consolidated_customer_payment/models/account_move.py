# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    consolidated_payment_id = fields.Many2one(
        comodel_name="consolidated.customer.payment",
        string="Pago consolidado",
        copy=False,
        index=True,
        ondelete="set null",
    )
    consolidated_payment_role = fields.Selection(
        selection=[
            ("receiver_payment", "Pago real receptor"),
            ("receiver_local", "Asignacion local receptora"),
            ("receiver_bridge", "Puente desde receptora"),
            ("target_bridge", "Puente destino"),
        ],
        string="Rol pago consolidado",
        copy=False,
    )

    def action_open_consolidated_payment(self):
        self.ensure_one()
        if not self.consolidated_payment_id:
            raise UserError(_("Este asiento no fue generado por un pago consolidado."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Pago consolidado"),
            "res_model": "consolidated.customer.payment",
            "view_mode": "form",
            "target": "current",
            "res_id": self.consolidated_payment_id.id,
        }
