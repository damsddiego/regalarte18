# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    card_settlement_source_journal_ids = fields.Many2many(
        related="company_id.card_settlement_source_journal_ids",
        readonly=False,
    )
    card_settlement_bank_journal_ids = fields.Many2many(
        related="company_id.card_settlement_bank_journal_ids",
        readonly=False,
    )
    card_settlement_bridge_account_ids = fields.Many2many(
        related="company_id.card_settlement_bridge_account_ids",
        readonly=False,
    )
    card_settlement_deduction_account_ids = fields.Many2many(
        related="company_id.card_settlement_deduction_account_ids",
        readonly=False,
    )
