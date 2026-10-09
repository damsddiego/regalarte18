# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # monto_venta pasó a calcularse desde la orden de venta. Odoo no
    # recalcula un campo que ya tenía columna, así que se llenan aquí los
    # seguimientos que ya tenían orden enlazada.
    env = api.Environment(cr, SUPERUSER_ID, {})
    Seg = env['sng.televentas.seguimiento']
    con_orden = Seg.search([('sale_order_id', '!=', False)])
    env.add_to_compute(Seg._fields['monto_venta'], con_orden)
    con_orden.flush_recordset(['monto_venta'])
    _logger.info(
        'sng_control_visitas: monto de televentas recalculado desde la orden '
        'en %s seguimientos', len(con_orden))
