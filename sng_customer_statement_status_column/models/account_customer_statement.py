# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools import SQL


class CustomerStatementCustomHandler(models.AbstractModel):
    _inherit = "account.customer.statement.report.handler"

    def _get_additional_column_aml_values(self):
        return SQL(
            "%(super_columns)s"
            "account_move.payment_state AS invoice_payment_status,",
            super_columns=super()._get_additional_column_aml_values(),
        )

    def _get_report_line_move_line(
        self,
        options,
        aml_query_result,
        partner_line_id,
        init_bal_by_col_group,
        level_shift=0,
    ):
        line = super()._get_report_line_move_line(
            options,
            aml_query_result,
            partner_line_id,
            init_bal_by_col_group,
            level_shift=level_shift,
        )

        for column in line["columns"]:
            if column.get("expression_label") == "invoice_payment_status":
                column.update({"name": "", "no_format": ""})
                if aml_query_result.get("move_type") == "out_invoice":
                    status_class = self._get_invoice_payment_status_class(
                        aml_query_result.get("invoice_payment_status")
                    )
                    if status_class:
                        column.update({
                            "name": "●",
                            "no_format": "●",
                            "class": f"o_customer_statement_status {status_class}",
                        })
                break

        return line

    def _get_invoice_payment_status_class(self, payment_state):
        if payment_state == "paid":
            return "o_customer_statement_status_paid"
        if payment_state in ("partial", "in_payment"):
            return "o_customer_statement_status_partial"
        if payment_state == "not_paid":
            return "o_customer_statement_status_unpaid"
        return ""
