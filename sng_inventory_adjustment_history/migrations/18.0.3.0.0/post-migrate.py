# -*- coding: utf-8 -*-
"""Crea una cabecera (sng.inventory.adjustment.batch) por cada solicitud de
ajuste existente que todavía no la tiene, conservando bodega, estado, solicitante
y datos de revisión. Antes de 18.0.3.0.0 cada solicitud era una sola existencia."""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT r.id, r.location_id, r.warehouse_id, r.company_id, r.state,
               r.requested_by_id, r.submitted_at, r.reviewed_by_id, r.reviewed_at,
               r.review_note, r.create_uid, r.create_date, r.write_uid, r.write_date
        FROM sng_inventory_adjustment_request r
        WHERE r.batch_id IS NULL
        ORDER BY r.id
    """)
    rows = cr.fetchall()
    for row in rows:
        (request_id, location_id, warehouse_id, company_id, state, requested_by_id,
         submitted_at, reviewed_by_id, reviewed_at, review_note,
         create_uid, create_date, write_uid, write_date) = row
        cr.execute("""
            INSERT INTO sng_inventory_adjustment_batch
                (location_id, warehouse_id, company_id, state, requested_by_id,
                 submitted_at, reviewed_by_id, reviewed_at, review_note,
                 create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (location_id, warehouse_id, company_id, state, requested_by_id,
              submitted_at, reviewed_by_id, reviewed_at, review_note,
              create_uid, create_date, write_uid, write_date))
        batch_id = cr.fetchone()[0]
        cr.execute(
            "UPDATE sng_inventory_adjustment_request SET batch_id = %s WHERE id = %s",
            (batch_id, request_id),
        )
    cr.execute("""
        UPDATE sng_inventory_adjustment_history h
        SET batch_id = r.batch_id
        FROM sng_inventory_adjustment_request r
        WHERE h.request_id = r.id AND h.batch_id IS DISTINCT FROM r.batch_id
    """)
    _logger.info("Solicitudes de ajuste migradas a cabecera: %s", len(rows))
