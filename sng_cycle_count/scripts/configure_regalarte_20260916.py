# -*- coding: utf-8 -*-
"""One-time, authorized cleanup. Run inside `odoo-bin shell`.

Defaults to rollback. Set APPLY=True in the shell's globals to commit.
Only the 39 explicitly approved sessions and warehouse 1 are in scope.
Holiday source: MTSS CARTA-MTSS-DAJ-AER-1076-2025 (official 2026 calendar).
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytz

from odoo import fields


APPLY = globals().get("APPLY", False)
SESSION_IDS = [45, 46, 47, 49, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88,
               90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103,
               105, 106, 107, 108, 109, 110, 111, 112, 113, 114]
REASON = (
    "Cancelación administrativa autorizada por el cliente el 16/09/2026. "
    "Las 39 sesiones anteriores ya no corresponden a los movimientos recientes "
    "de existencias. Se conserva su historial y se liberan sus cupos para iniciar "
    "el nuevo flujo de conteos. No se aplican diferencias ni ajustes de inventario."
)
SOURCE = "https://www.mtss.go.cr/temas-laborales/feriados/feriados_calendario_2026.pdf"
HOLIDAYS = [
    ("2026-01-01", "Año Nuevo"),
    ("2026-04-02", "Jueves Santo"),
    ("2026-04-03", "Viernes Santo"),
    ("2026-04-11", "Juan Santamaría"),
    ("2026-05-01", "Día Internacional del Trabajo"),
    ("2026-07-25", "Anexión del Partido de Nicoya"),
    ("2026-08-02", "Virgen de los Ángeles"),
    ("2026-08-15", "Día de la Madre"),
    ("2026-08-31", "Día de la Persona Negra y la Cultura Afrocostarricense"),
    ("2026-09-15", "Independencia"),
    ("2026-12-01", "Abolición del Ejército"),
    ("2026-12-25", "Navidad"),
]
TZ = pytz.timezone("America/Costa_Rica")


def utc(local_datetime):
    return TZ.localize(local_datetime).astimezone(pytz.utc).replace(tzinfo=None)


def rows(table, ids):
    # Table identifiers come only from constants in this script.
    env.cr.execute("SELECT to_jsonb(t) FROM " + table + " t WHERE id = ANY(%s) ORDER BY id", [ids])
    return [row[0] for row in env.cr.fetchall()]


def upsert(xml_name, model, values):
    record = env.ref("sng_cycle_count." + xml_name, raise_if_not_found=False)
    if record:
        if record._name != model:
            raise RuntimeError("Unexpected external identifier: " + xml_name)
        record.write(values)
    else:
        record = env[model].create(values)
        env["ir.model.data"].create({
            "module": "sng_cycle_count", "name": xml_name, "model": model,
            "res_id": record.id, "noupdate": True,
        })
    return record


def run():
    if APPLY and env.cr.dbname != "RegalarteProd":
        raise RuntimeError("Apply is restricted to the authorized production database.")
    env.cr.execute("SET LOCAL lock_timeout = '10s'")
    env.cr.execute("SET LOCAL statement_timeout = '120s'")
    counts = env["sng.cycle.count"].sudo().browse(SESSION_IDS).exists()
    warehouse = env["stock.warehouse"].browse(1)
    supervisor = env["res.users"].search([("login", "=", "admin2@regalartecr.com")])
    if len(counts) != 39 or warehouse.name != "Regalarte" or len(supervisor) != 1:
        raise RuntimeError("The approved sessions, warehouse or user no longer match.")
    if not supervisor.has_group("sng_cycle_count.group_cycle_count_supervisor"):
        raise RuntimeError("The selected user must already have the Jefatura role.")
    counts._lock_warehouses(warehouse)
    counts._lock_sessions()
    if any(count.wip_warehouse_ids != warehouse for count in counts):
        raise RuntimeError("A selected session belongs to another warehouse.")
    pending = counts.filtered(lambda count: count.state != "cancelled")
    if any(count.state not in ("draft", "in_progress", "pending_review", "pending_approval")
           for count in pending):
        raise RuntimeError("A selected session has already been applied.")
    if any(count.cancellation_reason != REASON for count in counts - pending):
        raise RuntimeError("A selected session was cancelled separately; review it first.")
    lines = counts.line_ids
    quants = lines.quant_id
    env.cr.execute("SELECT id FROM stock_quant WHERE id = ANY(%s) ORDER BY id FOR UPDATE", [quants.ids])
    quants.invalidate_recordset()
    if any(line.quant_id.sng_cycle_line_id != line for line in pending.line_ids):
        raise RuntimeError("A pending line no longer owns its inventory count.")
    requests = env["sng.inventory.adjustment.request"].search([
        ("quant_id", "in", quants.ids), ("state", "in", ["draft", "pending"]),
    ])
    if requests:
        raise RuntimeError("Manual adjustment requests overlap the approved sessions.")
    activities = env["mail.activity"].search([
        ("res_model", "=", "sng.cycle.count"), ("res_id", "in", counts.ids),
    ])
    snapshot = {
        "database": env.cr.dbname, "at_utc": str(fields.Datetime.now()),
        "mode": "apply" if APPLY else "dry-run", "reason": REASON,
        "holiday_source": SOURCE,
        "sessions": rows("sng_cycle_count", counts.ids),
        "lines": rows("sng_cycle_count_line", lines.ids),
        "quants": rows("stock_quant", quants.ids),
        "activities": rows("mail_activity", activities.ids),
        "warehouse": rows("stock_warehouse", warehouse.ids),
    }
    backup_dir = Path("/opt/odoo18/backups/sng_cycle_control/20260916")
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = backup_dir / (datetime.utcnow().strftime("%H%M%S%f") + "_" + snapshot["mode"] + ".json")
    with os.fdopen(os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as backup:
        json.dump(snapshot, backup, ensure_ascii=False, indent=2, default=str)

    calendar = upsert("regalarte_cycle_calendar", "resource.calendar", {
        "name": "Conteos cíclicos Regalarte — Costa Rica",
        "company_id": warehouse.company_id.id, "tz": "America/Costa_Rica",
        "attendance_ids": [fields.Command.clear()] + [fields.Command.create({
            "name": "Jornada de conteos", "dayofweek": str(day),
            "hour_from": 7.5, "hour_to": 17.0, "day_period": "morning",
        }) for day in range(5)],
    })
    for date_string, name in HOLIDAYS:
        day = datetime.strptime(date_string, "%Y-%m-%d")
        upsert("regalarte_cycle_holiday_" + date_string.replace("-", "_"), "resource.calendar.leaves", {
            "name": name, "calendar_id": calendar.id, "resource_id": False,
            "date_from": utc(day), "date_to": utc(day + timedelta(days=1)),
            "time_type": "leave",
        })
    warehouse.write({"cycle_supervisor_id": supervisor.id, "cycle_calendar_id": calendar.id})

    # Record the reason in chatter, but send no emails or inbox notifications.
    # Abort before any physical adjustment if an inherited cancellation changes.
    def no_adjustments(*args, **kwargs):
        raise RuntimeError("Administrative cancellation must never apply inventory.")

    with patch.object(type(counts), "_notify_thread", return_value=[]), \
            patch.object(type(quants), "_apply_inventory", no_adjustments):
        pending = pending.with_context(tracking_disable=True, mail_create_nosubscribe=True,
                                       mail_post_autofollow=False)
        pending.write({"cancellation_reason": REASON})
        pending.action_cancel()
    env.flush_all()
    counts.invalidate_recordset()
    lines.invalidate_recordset()
    quants.invalidate_recordset()
    if any(count.state != "cancelled" for count in counts) or any(line.state != "cancelled" for line in lines):
        raise RuntimeError("Incomplete cancellation.")
    if any(quant.sng_cycle_line_id or quant.inventory_quantity_set for quant in quants):
        raise RuntimeError("A cancelled count still holds an inventory proposal.")
    before_stock = {row["id"]: (row["quantity"], row["reserved_quantity"]) for row in snapshot["quants"]}
    after_stock = {row["id"]: (row["quantity"], row["reserved_quantity"])
                   for row in rows("stock_quant", quants.ids)}
    if before_stock != after_stock:
        raise RuntimeError("Physical or reserved stock changed; rolling back.")

    # Monday, a Tuesday holiday, a weekend and Holy Week all exercise the actual
    # production deadline method against the configured calendar.
    for registered, expected in [
        ("2026-09-21 10:00", "2026-09-23"),
        ("2026-09-14 10:00", "2026-09-17"),
        ("2026-11-30 10:00", "2026-12-03"),
        ("2026-12-24 18:00", "2026-12-29"),
        ("2026-04-01 10:00", "2026-04-07"),
    ]:
        warning, deadline = warehouse._cycle_deadlines(utc(datetime.strptime(registered, "%Y-%m-%d %H:%M")))
        expected_day = datetime.strptime(expected, "%Y-%m-%d")
        if warning != utc(expected_day.replace(hour=7, minute=30)) or deadline != utc(expected_day.replace(hour=17)):
            raise RuntimeError("Unexpected business-day deadline for " + registered)
    remaining = env["sng.cycle.count"].search_count([
        ("state", "in", ["draft", "in_progress", "pending_review", "pending_approval"]),
        ("wip_started", "=", True), ("wip_warehouse_ids", "in", warehouse.ids),
    ])
    result = {"cancelled_sessions": len(counts), "cancelled_lines": len(lines),
              "quants_stock_unchanged": len(quants), "remaining_wip": remaining,
              "supervisor": supervisor.login, "calendar_id": calendar.id,
              "holidays_2026": len(HOLIDAYS), "deadline_checks": 5,
              "backup": str(filename), "committed": APPLY}
    if APPLY:
        env.cr.commit()
    else:
        env.cr.rollback()
    print(json.dumps(result, ensure_ascii=False, indent=2))


try:
    run()
except Exception:
    env.cr.rollback()
    raise
