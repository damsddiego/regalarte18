# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    regalia_expense_account_id = fields.Many2one(
        related="company_id.regalia_expense_account_id",
        readonly=False,
    )
    regalia_counterpart_account_id = fields.Many2one(
        related="company_id.regalia_counterpart_account_id",
        readonly=False,
    )
    regalia_journal_id = fields.Many2one(
        related="company_id.regalia_journal_id",
        readonly=False,
    )
