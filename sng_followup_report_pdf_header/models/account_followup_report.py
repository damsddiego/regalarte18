# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools.misc import format_datetime


class AccountFollowupCustomHandler(models.AbstractModel):
    _inherit = "account.followup.report.handler"

    def _get_custom_display_config(self):
        display_config = super()._get_custom_display_config()
        pdf_export = dict(display_config.get("pdf_export", {}))
        pdf_export["pdf_export_filters"] = (
            "sng_followup_report_pdf_header.pdf_export_filters"
        )
        display_config["pdf_export"] = pdf_export
        return display_config

    def _sng_format_report_datetime(self):
        return format_datetime(
            self.env,
            fields.Datetime.now(),
            tz=self.env.user.tz,
        )
