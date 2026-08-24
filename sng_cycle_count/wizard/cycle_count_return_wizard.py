# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class CycleCountReturnWizard(models.TransientModel):
    _name = "sng.cycle.count.return.wizard"
    _description = "Devolver Conteo Cíclico para Reconteo"

    cycle_count_id = fields.Many2one(
        "sng.cycle.count",
        string="Conteo",
        required=True,
        readonly=True,
    )
    reason = fields.Text(string="Motivo de devolución", required=True)

    def action_confirm(self):
        self.ensure_one()
        count = self.cycle_count_id
        count._check_management_access()
        if count.state != "pending_approval":
            raise UserError(_("El conteo ya no está pendiente de aprobación."))

        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Debe indicar el motivo de la devolución."))

        count._lock_quants()
        changed_lines = count._get_lines_with_changed_stock()
        for line in changed_lines:
            line.sudo().write(
                {
                    "theoretical_qty": line.quant_id.quantity,
                    "counted_qty": 0.0,
                    "state": "pending",
                    "count_date": False,
                }
            )

        count._close_management_activities(
            _("Conteo devuelto por %s.") % self.env.user.display_name
        )
        count.sudo().write({"state": "in_progress"})
        count._notify_operator_recount(reason, changed_lines)
        return {"type": "ir.actions.act_window_close"}
