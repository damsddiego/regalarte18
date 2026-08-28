# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    total_invoiced_tax_incl = fields.Monetary(
        compute="_compute_total_invoiced_tax_incl",
        string="Total Invoiced (Tax Incl.)",
        groups="account.group_account_invoice,account.group_account_readonly",
    )

    @api.depends_context("company")
    def _compute_total_invoiced_tax_incl(self):
        self.total_invoiced_tax_incl = 0
        if not self.ids:
            return True

        all_partners_and_children = {}
        all_partner_ids = []
        for partner in self.filtered("id"):
            all_partners_and_children[partner] = self.with_context(active_test=False).search(
                [("id", "child_of", partner.id)]
            ).ids
            all_partner_ids += all_partners_and_children[partner]

        domain = [
            ("partner_id", "in", all_partner_ids),
            ("state", "not in", ["draft", "cancel"]),
            ("move_type", "in", ("out_invoice", "out_refund")),
        ]
        totals = self.env["account.move"]._read_group(
            domain, ["partner_id"], ["amount_total_signed:sum"]
        )
        for partner, child_ids in all_partners_and_children.items():
            partner.total_invoiced_tax_incl = sum(
                amount_sum for p, amount_sum in totals if p.id in child_ids
            )
