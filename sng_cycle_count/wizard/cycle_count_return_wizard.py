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

    line_ids = fields.Many2many(
        "sng.cycle.count.line", string="Líneas a recontar",
        domain="[('cycle_count_id', '=', cycle_count_id)]",
        help="Sin selección, se devolverán todas las líneas del conteo.",
    )

    def action_confirm(self):
        self.ensure_one()
        count = self.cycle_count_id
        count._check_supervisor()
        count._lock_sessions()
        if count.state not in ("pending_review", "pending_approval"):
            raise UserError(_("La sesión debe estar pendiente de revisión o aprobación."))
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Debe indicar el motivo de la devolución."))
        lines = self.line_ids or count.line_ids
        if any(line.cycle_count_id != count for line in lines):
            raise UserError(_("Las líneas deben pertenecer a esta sesión."))
        lines._check_independent_reviewer()
        lines._return_for_recount(reason)
        return {"type": "ir.actions.act_window_close"}
