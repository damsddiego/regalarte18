# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SngSalesRouteSalesReportWizard(models.TransientModel):
    _name = "sng.sales.route.sales.report.wizard"
    _description = "Wizard Reporte de Ventas por Ruta y Vendedor"

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(month=1, day=1)

    date_from = fields.Date(
        string="Desde",
        required=True,
        default=lambda self: self._default_date_from(),
    )
    date_to = fields.Date(
        string="Hasta",
        required=True,
        default=fields.Date.context_today,
    )
    include_zero = fields.Boolean(
        string="Incluir rutas y vendedores sin ventas",
        default=True,
        help="Muestra también las rutas y vendedores que no facturaron en el periodo.",
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _("La fecha inicial no puede ser posterior a la fecha final.")
                )

    def _rebuild(self):
        self.ensure_one()
        report_model = self.env["sng.sales.route.sales.report"]
        report_model._rebuild_snapshot(self.date_from, self.date_to, self.include_zero)
        return report_model

    def action_open_report(self):
        report_model = self._rebuild()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ventas por Ruta y Vendedor"),
            "res_model": report_model._name,
            "view_mode": "list",
            "domain": report_model._get_snapshot_domain(),
            "context": {
                "search_default_group_line_type": 1,
                "sng_srs_date_from": fields.Date.to_string(self.date_from),
                "sng_srs_date_to": fields.Date.to_string(self.date_to),
                "sng_srs_include_zero": self.include_zero,
                "create": False,
                "edit": False,
                "delete": False,
            },
        }

    def action_export_xlsx(self):
        report_model = self._rebuild()
        return report_model._get_xlsx_action(
            self.date_from, self.date_to, self.include_zero
        )
