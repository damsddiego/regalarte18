# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import Command, fields


def post_init_hook(env):
    """Prepare the Regalarte configuration without enabling automation."""
    Config = env["sng.biweekly.replenishment.config"].sudo()
    if Config.search_count([]):
        return

    warehouses = env["stock.warehouse"].sudo().search(
        [("code", "in", ["WH", "BBAPO", "BBAOD", "BBPOD"])]
    )
    by_code = {warehouse.code: warehouse for warehouse in warehouses}
    required_codes = {"WH", "BBAPO", "BBAOD", "BBPOD"}
    if not required_codes.issubset(by_code):
        return
    main = by_code["WH"]
    if any(warehouse.company_id != main.company_id for warehouse in warehouses):
        return

    group = env["sng.warehouse.group"].sudo().search(
        [("name", "ilike", "Inv Bod Reg")], limit=1
    )
    if not group or warehouses - group.warehouse_ids:
        return

    picking_types = env["stock.picking.type"].sudo().search(
        [
            ("warehouse_id", "=", main.id),
            "|",
            ("code", "=", "outgoing"),
            ("sequence_code", "in", ["RELL", "CONS", "REGOUT"]),
        ]
    )
    Config.create(
        {
            "name": "Reabastecimiento bisemanal - Regalarte",
            "active": True,
            "automation_active": False,
            "company_id": main.company_id.id,
            "warehouse_group_id": group.id,
            "main_warehouse_id": main.id,
            "coverage_days": 14,
            "safety_days": 2,
            "lead_time_days": 1,
            "cycle_interval_days": 14,
            "next_run_date": fields.Date.today() + timedelta(days=14),
            "demand_picking_type_ids": [Command.set(picking_types.ids)],
            "source_line_ids": [
                Command.create({"sequence": 10, "warehouse_id": by_code["BBAPO"].id}),
                Command.create({"sequence": 20, "warehouse_id": by_code["BBAOD"].id}),
                Command.create({"sequence": 30, "warehouse_id": by_code["BBPOD"].id}),
            ],
        }
    )
