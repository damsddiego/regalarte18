# -*- coding: utf-8 -*-

import calendar

from odoo import api, models


class ReportCommissionSettlement(models.AbstractModel):
    _name = "report.sng_sales_commission.report_commission_settlement"
    _description = "Reporte de liquidación de comisiones"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["sng.commission.settlement"].browse(docids)
        month_names = {str(month): calendar.month_name[month] for month in range(1, 13)}
        return {
            "doc_ids": docs.ids,
            "doc_model": "sng.commission.settlement",
            "docs": docs,
            "month_names": month_names,
        }


class ReportCommissionPaymentDetail(models.AbstractModel):
    _name = "report.sng_sales_commission.report_commission_payment_detail"
    _description = "Reporte de pagos de comisión"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["sng.commission.settlement"].browse(docids)
        month_names = {str(month): calendar.month_name[month] for month in range(1, 13)}
        payment_data_by_doc = {
            doc.id: doc._get_payment_report_data()
            for doc in docs
        }
        return {
            "doc_ids": docs.ids,
            "doc_model": "sng.commission.settlement",
            "docs": docs,
            "month_names": month_names,
            "payment_data_by_doc": payment_data_by_doc,
        }
