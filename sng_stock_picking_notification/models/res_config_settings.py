# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_notification_user_ids = fields.Many2many(
        related="company_id.stock_notification_user_ids",
        readonly=False,
    )
