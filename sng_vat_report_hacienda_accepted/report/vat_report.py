# -*- coding: utf-8 -*-
from odoo import models


class VATReport(models.AbstractModel):
    _inherit = "report.account_financial_report.vat_report"

    def _get_hacienda_accepted_domain(self):
        if "state_tributacion" not in self.env["account.move"]._fields:
            return []
        return [("move_id.state_tributacion", "=", "aceptado")]

    def _get_tax_report_domain(self, company_id, date_from, date_to, only_posted_moves):
        domain = super()._get_tax_report_domain(
            company_id, date_from, date_to, only_posted_moves
        )
        return list(domain) + self._get_hacienda_accepted_domain()

    def _get_net_report_domain(self, company_id, date_from, date_to, only_posted_moves):
        domain = super()._get_net_report_domain(
            company_id, date_from, date_to, only_posted_moves
        )
        return list(domain) + self._get_hacienda_accepted_domain()
