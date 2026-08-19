# -*- coding: utf-8 -*-

import logging

from odoo import api, SUPERUSER_ID


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
            UPDATE sng_commercial_plan
               SET period_mode = 'annual'
             WHERE period_mode IS NULL
        """
    )
    cr.execute(
        """
            UPDATE sng_commercial_plan_line AS line
               SET target_to_date_amount = line.target_amount * (
                    CASE
                        WHEN plan.target_year < EXTRACT(YEAR FROM CURRENT_DATE) THEN 12
                        WHEN plan.target_year > EXTRACT(YEAR FROM CURRENT_DATE) THEN 0
                        ELSE EXTRACT(MONTH FROM CURRENT_DATE)
                    END
               ) / 12.0
              FROM sng_commercial_plan AS plan
             WHERE line.plan_id = plan.id
        """
    )
    cr.execute(
        """
            UPDATE sng_commercial_plan
               SET state = 'draft'
             WHERE state = 'calculated'
        """
    )
    reset_count = cr.rowcount

    env = api.Environment(cr, SUPERUSER_ID, {})
    plans = env['sng.commercial.plan'].search([])
    plans.invalidate_recordset([
        'line_ids',
        'total_compliance_percent',
        'total_target_to_date',
    ])
    plans._compute_totals()
    _logger.info(
        'sng_plan_comercial_clientes: %s planes calculados regresados a borrador',
        reset_count,
    )
