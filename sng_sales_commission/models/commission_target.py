# -*- coding: utf-8 -*-

import calendar

from odoo import api, fields, models, _


MONTH_SELECTION = [(str(month), calendar.month_name[month]) for month in range(1, 13)]


class CommissionTarget(models.Model):
    _name = "sng.commission.target"
    _description = "Meta mensual de comisión"
    _order = "year desc, month desc, salesperson_id"

    _sql_constraints = [
        (
            "sng_commission_target_unique_period",
            "unique(plan_id, salesperson_id, year, month)",
            "Ya existe una meta para este vendedor, plan y periodo.",
        ),
    ]

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    plan_id = fields.Many2one("sng.commission.plan", string="Plan", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="plan_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="plan_id.currency_id", store=True, readonly=True)
    salesperson_id = fields.Many2one(
        "res.partner",
        string="Vendedor",
        required=True,
        domain="[('is_salesperson', '=', True)]",
    )
    year = fields.Integer(string="Año", required=True, default=lambda self: fields.Date.today().year)
    month = fields.Selection(MONTH_SELECTION, string="Mes", required=True, default=lambda self: str(fields.Date.today().month))
    target_amount = fields.Monetary(string="Meta", currency_field="currency_id", required=True)

    @api.depends("salesperson_id", "year", "month")
    def _compute_name(self):
        month_names = dict(MONTH_SELECTION)
        for record in self:
            month_name = month_names.get(record.month, "")
            salesperson = record.salesperson_id.display_name or _("Sin vendedor")
            record.name = f"{salesperson} - {month_name} {record.year}"
