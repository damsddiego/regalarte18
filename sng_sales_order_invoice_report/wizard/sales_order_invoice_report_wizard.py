# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SngSalesOrderInvoiceReportWizard(models.TransientModel):
    _name = "sng.sales.order.invoice.report.wizard"
    _description = "Wizard Reporte Ventas Ingresadas vs Facturadas"

    date_from = fields.Date(
        string="Fecha desde",
        required=True,
        default=lambda self: fields.Date.to_date(fields.Date.context_today(self)).replace(day=1),
    )
    date_to = fields.Date(
        string="Fecha hasta",
        required=True,
        default=fields.Date.context_today,
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="sng_so_inv_report_wiz_company_rel",
        column1="invoice_report_wizard_id",
        column2="company_rel_id",
        string="Companias",
        default=lambda self: self.env.companies,
    )
    salesperson_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="sng_so_inv_report_wiz_salesperson_rel",
        column1="invoice_report_wizard_id",
        column2="salesperson_partner_id",
        string="Vendedores",
        domain="[('is_salesperson', '=', True)]",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="sng_so_inv_report_wiz_partner_rel",
        column1="invoice_report_wizard_id",
        column2="customer_partner_id",
        string="Clientes",
        domain="[('customer_rank', '>', 0)]",
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError(_("La fecha inicial debe ser menor o igual a la fecha final."))

    def _get_run_kwargs(self):
        self.ensure_one()
        company_ids = self.company_ids.ids or self.env.context.get("allowed_company_ids") or self.env.companies.ids
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_ids": company_ids,
            "partner_ids": self.partner_ids.ids,
            "salesperson_ids": self.salesperson_ids.ids,
        }

    def _rebuild_snapshot_from_wizard(self):
        self.ensure_one()
        report_model = self.env["sng.sales.order.invoice.report"]
        kwargs = self._get_run_kwargs()
        report_model._rebuild_snapshot(**kwargs)
        return report_model, kwargs

    def action_open_report(self):
        self.ensure_one()
        report_model, kwargs = self._rebuild_snapshot_from_wizard()
        action = self.env.ref(
            "sng_sales_order_invoice_report.action_sng_sales_order_invoice_report"
        ).read()[0]
        action["domain"] = report_model._get_snapshot_domain(self.date_from, self.date_to)
        action["context"] = {
            "search_default_group_by_salesperson": 1,
            "create": False,
            "edit": False,
            "delete": False,
            "allowed_company_ids": kwargs["company_ids"],
        }
        return action

    def action_export_xlsx(self):
        self.ensure_one()
        self._rebuild_snapshot_from_wizard()
        return self.env.ref(
            "sng_sales_order_invoice_report.action_sng_sales_order_invoice_report_xlsx"
        ).report_action(self)
