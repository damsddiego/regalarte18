# -*- coding: utf-8 -*-

from odoo import api, models


class ReportSalesRouteSales(models.AbstractModel):
    _name = "report.sng_sales_routes.report_sales_route_sales"
    _description = "Reporte PDF de Ventas por Ruta y Vendedor"

    def _prepare_section(self, lines):
        return {
            "lines": lines,
            "total_amount": sum(lines.mapped("amount_total")),
            "total_untaxed": sum(lines.mapped("amount_untaxed")),
            "total_weight": sum(lines.mapped("weight")),
            "total_count": sum(lines.mapped("invoice_count")),
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["sng.sales.route.sales.report.wizard"].browse(docids)
        report_model = self.env["sng.sales.route.sales.report"]
        lines = report_model.search(
            report_model._get_snapshot_domain(), order="line_type, sequence, name"
        )
        wiz = wizard[:1]
        client_lines = self.env["sng.sales.route.client.report"].browse()
        if wiz.include_detail:
            client_model = self.env["sng.sales.route.client.report"]
            client_lines = client_model.search(client_model._get_snapshot_domain())
        return {
            "doc_ids": docids,
            "doc_model": "sng.sales.route.sales.report.wizard",
            "docs": wizard,
            "company": self.env.company,
            "currency": self.env.company.currency_id,
            "date_from": wizard[:1].date_from,
            "date_to": wizard[:1].date_to,
            "route_section": self._prepare_section(
                lines.filtered(lambda line: line.line_type == "route")
            ),
            "salesperson_section": self._prepare_section(
                lines.filtered(lambda line: line.line_type == "salesperson")
            ),
            "weight_base": wiz.weight_base,
            "client_lines": client_lines,
            "client_total": sum(client_lines.mapped("amount_total")),
            "client_total_untaxed": sum(client_lines.mapped("amount_untaxed")),
        }
