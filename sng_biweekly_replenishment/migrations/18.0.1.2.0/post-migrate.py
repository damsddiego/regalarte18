# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Ciclos previos a las cajas: la necesidad era la cantidad sugerida."""
    cr.execute(
        """
        UPDATE sng_biweekly_replenishment_line
           SET need_qty = suggested_qty,
               without_box = TRUE
         WHERE need_qty IS NULL
        """
    )
