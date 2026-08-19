# -*- coding: utf-8 -*-
from odoo import models


class AccountReport(models.Model):
    _inherit = "account.report"

    def _is_hacienda_accepted_tax_report(self):
        generic_tax_report = self.env.ref(
            "account.generic_tax_report", raise_if_not_found=False
        )
        if not generic_tax_report:
            return False
        return any(
            report == generic_tax_report
            or report.root_report_id == generic_tax_report
            for report in self
        )

    def _get_options_domain(self, options, date_scope):
        domain = super()._get_options_domain(options, date_scope)
        if (
            "state_tributacion" in self.env["account.move"]._fields
            and self._is_hacienda_accepted_tax_report()
        ):
            domain += [("move_id.state_tributacion", "=", "aceptado")]
        return domain
