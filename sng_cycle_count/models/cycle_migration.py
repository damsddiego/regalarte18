# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero

from .cycle_control import OPEN_STATES


class CycleCountMigration(models.Model):
    _inherit = "sng.cycle.count"

    @api.model
    def _migrate_cycle_controls(self):
        """One-time upgrade, preserving history and granting only one grace period."""
        params = self.env["ir.config_parameter"].sudo()
        key = "sng_cycle_count.control_migrated_at"
        if params.get_param(key):
            return
        now = fields.Datetime.now()
        counts = self.sudo().search([("state", "in", OPEN_STATES)])
        for count in counts:
            warehouses = count.line_ids.location_id.warehouse_id or count.config_id.location_ids.warehouse_id
            if not warehouses or any(not l.location_id.warehouse_id for l in count.line_ids):
                raise UserError(_("Antes de actualizar, asigne las ubicaciones de %s a una bodega física.") % count.name)
            count._system_write({"warehouse_id": warehouses[:1].id,
                                 "wip_warehouse_ids": [fields.Command.set(warehouses.ids)],
                                 "wip_started": True})
            for line in count.line_ids:
                other = self.env["sng.cycle.count.line"].sudo().search_count([
                    ("quant_id", "=", line.quant_id.id), ("cycle_count_id.state", "in", OPEN_STATES),
                    ("id", "!=", line.id),
                ])
                if other:
                    raise UserError(_("Resuelva las sesiones duplicadas de %s antes de actualizar.") % line.product_id.display_name)
                requests = self.env["sng.inventory.adjustment.request"].sudo().search_count([
                    ("quant_id", "=", line.quant_id.id), ("state", "in", ["draft", "pending"]),
                ])
                if requests:
                    raise UserError(_("Resuelva la solicitud manual que coincide con %s antes de actualizar.") % count.name)
                values = {"review_state": "review" if line.state == "counted" else "capture"}
                # Older versions did not record individual captures. Keep all known
                # actors conservatively; unidentified lines require a fresh capture.
                users = count.user_id | count.submitted_by_id
                if line.state == "counted":
                    values.update(counted_by_ids=[fields.Command.set(users.ids)],
                                  last_counted_by_id=count.user_id.id or count.submitted_by_id.id)
                if line.state == "counted" and not float_is_zero(line.difference_qty,
                                                                                precision_rounding=line.product_uom_id.rounding):
                    warning, deadline = line.location_id.warehouse_id._cycle_deadlines(now)
                    values.update(first_difference_at=line.count_date or now, warning_at=warning, deadline_at=deadline)
                line._control_write(values)
                line.quant_id.sudo().write({"sng_cycle_line_id": line.id})
                if line.state == "counted":
                    line._sync_quant()
                line._audit("migration", _("Activación de controles; participantes anteriores inferidos de la sesión."))
            if count.state == "pending_approval":
                count._system_write({"state": "pending_review"})
                count._close_management_activities(_("Se requiere visto bueno de Jefatura antes de aprobar."))
        params.set_param(key, fields.Datetime.to_string(now))
