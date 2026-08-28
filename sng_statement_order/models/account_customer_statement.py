# -*- coding: utf-8 -*-
from datetime import date

from odoo import models
from odoo.tools import SQL


class CustomerStatementCustomHandler(models.AbstractModel):
    _inherit = "account.customer.statement.report.handler"

    def _get_additional_column_aml_values(self):
        """Agrega move_id a los valores extra seleccionados para poder
        agrupar posteriormente por documento contable."""
        return SQL(
            "%(super_columns)s"
            "account_move_line.move_id AS move_id,",
            super_columns=super()._get_additional_column_aml_values(),
        )

    def _get_aml_values(self, options, partner_ids, offset=0, limit=None):
        """Trae todos los apuntes del partner (sin paginación SQL) para poder
        reordenarlos en Python agrupando facturas con sus pagos/NC.
        Luego aplica offset y limit manualmente para respetar la paginación
        del reporte."""
        all_results = super()._get_aml_values(
            options, partner_ids, offset=0, limit=None
        )

        for partner_id in partner_ids:
            all_results[partner_id] = self._sort_aml_results_by_invoice_group(
                all_results[partner_id]
            )

        if offset or limit:
            for partner_id in partner_ids:
                results = all_results[partner_id]
                if offset:
                    results = results[offset:]
                if limit:
                    results = results[:limit]
                all_results[partner_id] = results

        return all_results

    def _get_aml_group_mapping(self, aml_results):
        """Devuelve un dict: aml_id -> {group_move_id, group_date}

        Para cada línea reconciliada con una factura de cliente (out_invoice),
        devuelve el move_id y la fecha de esa factura para poder agrupar
        los documentos relacionados bajo la misma factura.
        """
        if not aml_results:
            return {}

        aml_ids = tuple(r["id"] for r in aml_results)
        if not aml_ids:
            return {}

        self.env.cr.execute(
            """
            WITH reconciled_facts AS (
                -- Reconciliaciones parciales contra facturas de cliente
                SELECT
                    CASE WHEN pr.debit_move_id IN %(aml_ids)s
                        THEN pr.debit_move_id
                        ELSE pr.credit_move_id
                    END AS aml_id,
                    am.id AS invoice_move_id,
                    am.date AS invoice_date
                FROM account_partial_reconcile pr
                JOIN account_move_line counterpart
                    ON counterpart.id = CASE
                        WHEN pr.debit_move_id IN %(aml_ids)s
                            THEN pr.credit_move_id
                        ELSE pr.debit_move_id
                    END
                JOIN account_move am ON am.id = counterpart.move_id
                WHERE (
                    pr.debit_move_id IN %(aml_ids)s
                    OR pr.credit_move_id IN %(aml_ids)s
                )
                  AND am.move_type = 'out_invoice'

                UNION

                -- Reconciliaciones completas contra facturas de cliente
                SELECT
                    aml.id AS aml_id,
                    am.id AS invoice_move_id,
                    am.date AS invoice_date
                FROM account_move_line aml
                JOIN account_move_line counterpart
                    ON counterpart.full_reconcile_id = aml.full_reconcile_id
                    AND counterpart.id != aml.id
                JOIN account_move am ON am.id = counterpart.move_id
                WHERE aml.id IN %(aml_ids)s
                  AND aml.full_reconcile_id IS NOT NULL
                  AND am.move_type = 'out_invoice'
            )
            SELECT
                aml_id,
                MIN(invoice_move_id) AS invoice_move_id,
                MIN(invoice_date) AS invoice_date
            FROM reconciled_facts
            WHERE invoice_move_id IS NOT NULL
            GROUP BY aml_id
            """,
            {"aml_ids": aml_ids},
        )

        return {
            row["aml_id"]: {
                "group_move_id": row["invoice_move_id"],
                "group_date": row["invoice_date"],
            }
            for row in self.env.cr.dictfetchall()
        }

    def _sort_aml_results_by_invoice_group(self, aml_results):
        """Ordena los apuntes para que cada factura aparezca seguida de los
        pagos y notas de crédito que la afectan.

        Criterio de orden:
        1. Fecha del grupo (fecha de la factura raíz).
        2. ID del move del grupo (para mantener grupos separados del mismo día).
        3. Tipo de línea: factura primero, luego pagos/NC reconciliados,
           y al final lo no reconciliado.
        4. Fecha de la línea.
        5. ID del apunte (desempate estable).
        """
        if not aml_results:
            return aml_results

        group_mapping = self._get_aml_group_mapping(aml_results)

        def sort_key(result):
            is_invoice = result["move_type"] == "out_invoice"

            if is_invoice:
                group_date = (
                    result.get("invoice_date")
                    or result.get("date_maturity")
                    or date.min
                )
                group_move_id = result.get("move_id") or 0
                sort_priority = 0
            else:
                group_info = group_mapping.get(result["id"])
                if group_info:
                    group_date = group_info["group_date"] or date.min
                    group_move_id = group_info["group_move_id"] or 0
                    sort_priority = 1
                else:
                    group_date = (
                        result.get("invoice_date")
                        or result.get("date_maturity")
                        or date.min
                    )
                    group_move_id = result.get("move_id") or 0
                    sort_priority = 2

            line_date = (
                result.get("invoice_date")
                or result.get("date_maturity")
                or date.min
            )

            return (
                group_date,
                group_move_id,
                sort_priority,
                line_date,
                result["id"],
            )

        return sorted(aml_results, key=sort_key)
