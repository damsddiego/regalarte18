# -*- coding: utf-8 -*-
"""Run with odoo-bin shell on a disposable *_test_* database only.

Creates and commits isolated, empty test sessions; no inventory is adjusted.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from psycopg2.errors import SerializationFailure, DeadlockDetected
from odoo import api, fields, SUPERUSER_ID
from odoo.exceptions import UserError

if '_test_' not in env.cr.dbname:  # noqa: F821 - injected by odoo shell
    raise RuntimeError('Use únicamente una base de pruebas con _test_ en su nombre.')

registry = env.registry
suffix = uuid4().hex[:4]
warehouse = env['stock.warehouse'].create({'name': 'Concurrency ' + suffix, 'code': suffix})
config = env['sng.cycle.count.config'].create({'name': 'Concurrency ' + suffix, 'active': False})
values = {'warehouse_id': warehouse.id, 'config_id': config.id, 'count_date': fields.Date.today(),
          'user_id': SUPERUSER_ID, 'company_id': warehouse.company_id.id}
for _ in range(2):
    env['sng.cycle.count'].create(values)
env.cr.commit()
barrier = Barrier(2)


def create_third():
    for attempt in range(4):
        with registry.cursor() as cr:
            worker = api.Environment(cr, SUPERUSER_ID, {})
            cr.execute('SELECT count(*) FROM sng_cycle_count')
            if attempt == 0:
                barrier.wait(timeout=15)
            try:
                record = worker['sng.cycle.count'].create(values)
                cr.commit()
                return ('created', record.id)
            except (SerializationFailure, DeadlockDetected):
                cr.rollback()
            except UserError as error:
                cr.rollback()
                assert '3 o más' in str(error), str(error)
                return ('blocked', None)
    raise AssertionError('No se pudo resolver la transacción concurrente.')


try:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_third(), range(2)))
    env.cr.rollback()
    env.invalidate_all()
    sessions = env['sng.cycle.count'].search([('warehouse_id', '=', warehouse.id)])
    assert len(sessions) == 3, len(sessions)
    assert sorted(result[0] for result in results) == ['blocked', 'created'], results
    print('PASS: dos solicitudes simultáneas, un tercer cupo concedido y una cuarta sesión bloqueada.')
finally:
    env.cr.rollback()
    env.invalidate_all()
    sessions = env['sng.cycle.count'].search([('warehouse_id', '=', warehouse.id)])
    sessions._system_write({'wip_started': False})
    sessions.unlink()
    config.unlink()
    warehouse.active = False
    env.cr.commit()
