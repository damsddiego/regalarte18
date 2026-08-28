# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountReport(models.Model):
    _inherit = "account.report"

    def _get_pdf_export_html(self, options, lines, additional_context=None, template=None):
        # Inject the generation timestamp (in the user's timezone) so the PDF
        # header can show when the report was generated.
        additional_context = dict(additional_context or {})
        additional_context.setdefault(
            "report_generation_datetime",
            fields.Datetime.context_timestamp(self, fields.Datetime.now()),
        )
        return super()._get_pdf_export_html(
            options, lines, additional_context=additional_context, template=template
        )
