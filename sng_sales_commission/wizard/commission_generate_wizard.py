# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import UserError

from ..models.commission_target import MONTH_SELECTION


class CommissionGenerateWizard(models.TransientModel):
    _name = "sng.commission.generate.wizard"
    _description = "Generador de liquidaciones de comisión"

    plan_id = fields.Many2one("sng.commission.plan", string="Plan", required=True)
    company_id = fields.Many2one(related="plan_id.company_id", readonly=True)
    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.today().year)
    month = fields.Selection(MONTH_SELECTION, string="Mes", required=True, default=lambda self: str(fields.Date.today().month))
    salesperson_ids = fields.Many2many(
        "res.partner",
        "sng_commission_generate_wizard_partner_rel",
        "wizard_id",
        "partner_id",
        string="Vendedores",
        domain="[('is_salesperson', '=', True)]",
    )

    def action_generate(self):
        self.ensure_one()
        salespersons = self.salesperson_ids or self.env["res.partner"].search([("is_salesperson", "=", True)])
        if not salespersons:
            raise UserError(_("No hay vendedores configurados para generar liquidaciones."))

        settlements = self.env["sng.commission.settlement"]
        blocked = self.env["sng.commission.settlement"]
        for salesperson in salespersons:
            settlement = self.env["sng.commission.settlement"].search(
                [
                    ("plan_id", "=", self.plan_id.id),
                    ("salesperson_id", "=", salesperson.id),
                    ("year", "=", self.year),
                    ("month", "=", self.month),
                ],
                limit=1,
            )
            if settlement and settlement.state in ("approved", "closed"):
                blocked |= settlement
                continue
            if not settlement:
                settlement = self.env["sng.commission.settlement"].create(
                    {
                        "plan_id": self.plan_id.id,
                        "salesperson_id": salesperson.id,
                        "year": self.year,
                        "month": self.month,
                    }
                )
            settlement.action_generate_settlement()
            settlements |= settlement

        if blocked:
            raise UserError(
                _("No se pueden recalcular liquidaciones aprobadas o cerradas: %s")
                % ", ".join(blocked.mapped("display_name"))
            )

        return {
            "name": _("Liquidaciones"),
            "type": "ir.actions.act_window",
            "res_model": "sng.commission.settlement",
            "view_mode": "list,form",
            "domain": [("id", "in", settlements.ids)],
        }
