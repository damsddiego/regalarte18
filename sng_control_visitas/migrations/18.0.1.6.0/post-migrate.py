# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # El monto de televentas ya no se acredita cuando la gestión se cerró
    # con un resultado que no es de venta. Había seguimientos cerrados como
    # "datos incorrectos" o "reprogramar llamada" cargando el monto de una
    # orden enlazada, que inflaba la venta recuperada por televentas.
    env = api.Environment(cr, SUPERUSER_ID, {})
    Seg = env['sng.televentas.seguimiento']
    con_orden = Seg.search([('sale_order_id', '!=', False)])
    if not con_orden:
        return
    antes = sum(con_orden.mapped('monto_venta'))
    env.add_to_compute(Seg._fields['monto_venta'], con_orden)
    con_orden.flush_recordset(['monto_venta'])
    _logger.info(
        'sng_control_visitas: monto de televentas recalculado en %s '
        'seguimientos con orden (antes %s, ahora %s)',
        len(con_orden), antes, sum(con_orden.mapped('monto_venta')))
