# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SngNewReactivatedCustomerReportWizard(models.TransientModel):
    _name = "sng.new.reactivated.customer.report.wizard"
    _description = "Wizard Clientes Nuevos-React"

    month_date = fields.Date(
        string="Mes",
        required=True,
        default=lambda self: fields.Date.to_date(fields.Date.context_today(self)).replace(day=1),
        help="Seleccione cualquier fecha del mes que desea analizar.",
    )
    inactivity_months = fields.Integer(
        string="Meses sin compra",
        required=True,
        default=6,
        help="Cantidad minima de meses sin compras para considerar un cliente como reactivado.",
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="sng_new_react_report_wiz_company_rel",
        column1="wizard_id",
        column2="company_id",
        string="Companias",
        default=lambda self: self.env.companies,
    )

    @api.constrains("inactivity_months")
    def _check_inactivity_months(self):
        for wizard in self:
            if wizard.inactivity_months <= 0:
                raise UserError(_("Los meses sin compra deben ser mayores a cero."))

    def action_open_report(self):
        self.ensure_one()
        company_ids = self.company_ids.ids or self.env.context.get("allowed_company_ids") or self.env.companies.ids
        report_model = self.env["sng.new.reactivated.customer.report"]
        date_from, date_to = report_model._rebuild_snapshot(
            month_date=self.month_date,
            inactivity_months=self.inactivity_months,
            company_ids=company_ids,
        )
        action = self.env.ref(
            "sng_clientes_react.action_sng_new_reactivated_customer_report"
        ).sudo().read()[0]
        action["domain"] = report_model._get_snapshot_domain(date_from, date_to)
        action["context"] = {
            "create": False,
            "edit": False,
            "delete": False,
            "allowed_company_ids": company_ids,
            "search_default_group_by_type": 1,
        }
        return action
