# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    sng_ai_fec_proposal_id = fields.Many2one(
        "sng.ai.fec.proposal",
        string="Propuesta de digitalización FEC",
        copy=False,
        readonly=True,
        index=True,
    )

