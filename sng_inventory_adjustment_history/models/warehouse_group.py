# -*- coding: utf-8 -*-

from odoo import fields, models


class SngWarehouseGroup(models.Model):
    _inherit = "sng.warehouse.group"

    adjustment_history_count = fields.Integer(
        string="Ajustes de inventario",
        compute="_compute_adjustment_history_count",
    )
    adjustment_notify_emails = fields.Char(
        string="Correos de alerta de ajustes",
        help="Direcciones de correo separadas por comas. Cada vez que se "
        "apliquen ajustes de inventario en almacenes de este grupo se "
        "enviará un correo resumen a estas direcciones.",
    )

    def _compute_adjustment_history_count(self):
        history_model = self.env["sng.inventory.adjustment.history"]
        for group in self:
            group.adjustment_history_count = history_model.search_count(
                [("warehouse_group_ids", "in", group.id)]
            )

    def action_view_inventory_adjustment_history(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sng_inventory_adjustment_history.action_inventory_adjustment_history"
        )
        action["domain"] = [("warehouse_group_ids", "in", self.id)]
        action["context"] = {
            "search_default_group_by_warehouse": 1,
        }
        return action

