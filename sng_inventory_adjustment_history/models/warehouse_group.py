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
    adjustment_sender_email = fields.Char(
        string="Correo remitente de alertas",
        help="Correo utilizado como remitente de las alertas de ajustes. "
        "Si se deja vacío, se utilizará el correo de la compañía y, "
        "como último respaldo, el correo del usuario que aplica el ajuste.",
    )
    adjustment_approval_emails = fields.Char(
        string="Correos de Gerencia para aprobación",
        help="Destinatarios de las solicitudes de aprobación, separados por comas. "
        "Si está vacío, se usan los correos de alerta del grupo. "
        "Recibir el correo no otorga permisos: Gerencia debe tener el permiso de aprobación.",
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
