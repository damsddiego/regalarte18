# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Ciclos previos: lo que la regla de caja dejó sin sugerir."""
    cr.execute(
        """
        UPDATE sng_biweekly_replenishment_line
           SET box_skipped_qty = GREATEST(need_qty - suggested_qty, 0),
               min_box_applied = FALSE,
               not_sent_by_box = (need_qty - suggested_qty > 0
                                  AND COALESCE(suggested_qty, 0) = 0)
         WHERE box_skipped_qty IS NULL
           AND COALESCE(box_qty, 0) > 0
        """
    )
