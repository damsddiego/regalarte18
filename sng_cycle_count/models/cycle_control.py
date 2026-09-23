# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .cycle_count import MANAGEMENT_GROUP, SUPERVISOR_GROUP

_logger = logging.getLogger(__name__)
OPEN_STATES = ("draft", "in_progress", "pending_review", "pending_approval")
WIP_MESSAGE = "Bloqueo de Inventario: Tienes 3 o más conteos cíclicos pendientes de revisión/cierre. Debes resolver y aplicar las diferencias pendientes antes de iniciar un nuevo ciclo."
OVERDUE_ACTIVITY = "sng_cycle_count.mail_activity_cycle_count_overdue"


class CycleCountControl(models.Model):
    _inherit = "sng.cycle.count"

    state = fields.Selection(selection_add=[("pending_review", "Revisión de Jefatura")],
                             ondelete={"pending_review": "set default"})
    warehouse_id = fields.Many2one("stock.warehouse", string="Bodega física", copy=True)
    wip_warehouse_ids = fields.Many2many(
        "stock.warehouse", "sng_cycle_wip_warehouse_rel", "count_id", "warehouse_id",
        string="Bodegas del cupo", readonly=True, copy=False,
    )
    wip_started = fields.Boolean(string="Cupo ocupado", readonly=True, copy=False, index=True)
    cancellation_reason = fields.Text(string="Motivo de cancelación")

    def _check_supervisor(self):
        self.check_access("write")
        if not self.env.su and not self.env.user.has_group(SUPERVISOR_GROUP):
            raise AccessError(_("Solo Jefatura puede realizar esta acción."))

    def _system_write(self, vals):
        return super(CycleCountControl, self.sudo()).write(vals)

    @api.model
    def _lock_warehouses(self, warehouses):
        # The UPDATE is deliberate: at REPEATABLE READ, merely locking a row
        # would leave a stale snapshot after another transaction consumed a slot.
        ids = sorted(warehouses.ids)
        if ids:
            self.env.cr.execute(
                "UPDATE stock_warehouse SET cycle_lock_version = COALESCE(cycle_lock_version, 0) + 1 "
                "WHERE id = ANY(%s)", [ids],
            )
            warehouses.invalidate_recordset(["cycle_lock_version"])

    @api.model
    def _check_capacity(self, warehouses):
        self._lock_warehouses(warehouses)
        self.flush_model(["state", "wip_started", "wip_warehouse_ids"])
        for warehouse in warehouses:
            if self.sudo().search_count([
                ("state", "in", OPEN_STATES), ("wip_started", "=", True),
                ("wip_warehouse_ids", "in", warehouse.ids),
            ]) >= 3:
                raise UserError(_(WIP_MESSAGE))

    def _lock_sessions(self):
        self.check_access("write")
        self.flush_recordset()
        if self:
            self.env.cr.execute(
                "UPDATE sng_cycle_count SET write_date = write_date WHERE id = ANY(%s)",
                [sorted(self.ids)],
            )
            self.invalidate_recordset()

    @api.model_create_multi
    def create(self, vals_list):
        self._check_supervisor()
        records = self.browse()
        with self.env.cr.savepoint():
            for original in vals_list:
                vals = dict(original)
                if not self.env.su and {"wip_started", "wip_warehouse_ids", "approved_by_id", "approved_at",
                                        "submitted_by_id", "submitted_at"}.intersection(vals):
                    raise AccessError(_("Los datos de control son administrados por el servidor."))
                warehouse = self.env["stock.warehouse"].browse(vals.get("warehouse_id"))
                if not warehouse:
                    config = self.env["sng.cycle.count.config"].browse(vals.get("config_id"))
                    warehouse = config.location_ids.warehouse_id
                    if not warehouse:
                        warehouse = self.env["stock.warehouse"].search([
                            ("company_id", "=", vals.get("company_id", self.env.company.id)),
                        ], limit=2)
                if len(warehouse) != 1:
                    raise ValidationError(_("Seleccione una única bodega física para la sesión."))
                warehouse.check_access("read")
                if warehouse.company_id.id != vals.get("company_id", self.env.company.id):
                    raise ValidationError(_("La bodega y el conteo deben pertenecer a la misma compañía."))
                self._check_capacity(warehouse)
                operator = vals.get("user_id", self.default_get(["user_id"]).get("user_id"))
                vals.update(warehouse_id=warehouse.id, user_id=False, wip_started=False,
                            wip_warehouse_ids=[fields.Command.set(warehouse.ids)])
                # Initial lines are created before this order consumes its slot.
                record = super().create([vals])
                record._system_write({"user_id": operator, "wip_started": bool(operator)})
                records |= record
        return records

    def write(self, vals):
        if not self.env.su:
            if {"warehouse_id", "wip_warehouse_ids", "wip_started", "submitted_by_id", "submitted_at",
                "approved_by_id", "approved_at"}.intersection(vals):
                raise AccessError(_("No puede modificar la bodega o la auditoría del conteo."))
            if {"config_id", "company_id", "user_id", "count_date", "cancellation_reason"}.intersection(vals):
                self._check_supervisor()
            if "line_ids" in vals:
                # Operators may edit existing counts, but cannot link/create/remove lines.
                if not self.env.user.has_group(SUPERVISOR_GROUP) and any(c[0] != 1 for c in vals["line_ids"]):
                    raise AccessError(_("El operador solo puede capturar cantidades y observaciones."))
            if any(c.state == "pending_review" for c in self) and {"count_date", "config_id", "user_id", "company_id"}.intersection(vals):
                raise UserError(_("Devuelva las líneas para reconteo antes de modificar la sesión."))
            if "company_id" in vals and any(c.company_id.id != vals["company_id"] for c in self):
                raise AccessError(_("No puede trasladar una sesión a otra compañía."))
        if vals.get("user_id"):
            self._lock_warehouses(self.wip_warehouse_ids)
            self._lock_sessions()
            for count in self.filtered(lambda c: not c.wip_started and c.state in OPEN_STATES):
                self._check_capacity(count.wip_warehouse_ids)
                count._system_write({"wip_started": True})
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda c: c.wip_started or c.line_ids.capture_ids):
            raise UserError(_("Conserve el historial: cancele la sesión con un motivo, no la elimine."))
        return super().unlink()

    def action_start(self):
        self._lock_warehouses(self.wip_warehouse_ids)
        self._lock_sessions()
        for count in self:
            if not count.wip_started:
                self._check_capacity(count.wip_warehouse_ids)
                count._system_write({"user_id": count.user_id.id or self.env.uid, "wip_started": True})
        return super().action_start()

    def action_submit_for_approval(self):
        self._lock_sessions()
        for count in self:
            if count.state not in ("draft", "in_progress") or not count.line_ids:
                raise UserError(_("El conteo debe estar en captura y contener líneas."))
            if any(line.state != "counted" for line in count.line_ids):
                raise UserError(_("Registre todas las cantidades antes de enviar a Jefatura."))
            count.line_ids._send_for_review()
            count._system_write({"state": "pending_review", "submitted_by_id": self.env.uid,
                                 "submitted_at": fields.Datetime.now()})
            count.message_post(body=_("Conteo enviado a revisión de Jefatura."))
        return True

    def action_send_management(self):
        self._check_supervisor()
        self._lock_sessions()
        for count in self:
            if count.state != "pending_review":
                raise UserError(_("El conteo debe estar en revisión de Jefatura."))
            if any(line.review_state != "approved" or line.state != "counted" for line in count.line_ids):
                raise UserError(_("Todas las líneas deben tener el visto bueno de Jefatura."))
            users = count._get_management_users()
            if not users:
                raise UserError(_("Configure al menos un usuario activo de Gerencia para esta compañía."))
            count._system_write({"state": "pending_approval"})
            count._refresh_line_unit_costs()
            count._generate_discrepancy_reports()
            count._notify_management(users)
        return True

    def action_approve(self):
        self._check_management_access()
        self._lock_warehouses(self.wip_warehouse_ids)
        self._lock_sessions()
        self.line_ids._check_independent_reviewer()
        if any(line.review_state != "approved" for line in self.line_ids):
            raise UserError(_("Falta el visto bueno de Jefatura."))
        result = super().action_approve()
        self.line_ids._control_write({"applied_by_id": self.env.uid, "applied_at": fields.Datetime.now()})
        self.line_ids._release_quants()
        self._close_overdue_activities()
        return result

    def action_cancel(self):
        self._check_management_access()
        self._lock_warehouses(self.wip_warehouse_ids)
        self._lock_sessions()
        for count in self:
            if count.state not in OPEN_STATES or not (count.cancellation_reason or "").strip():
                raise UserError(_("Indique un motivo para cancelar una sesión abierta."))
            count.line_ids._control_write({"state": "cancelled"})
            count._system_write({"state": "cancelled"})
            count.line_ids._release_quants()
            count._close_management_activities(_("Sesión cancelada."))
            count.message_post(body=_("Sesión cancelada: %s") % count.cancellation_reason)
        self._close_overdue_activities()
        return True

    def action_copy_theoretical(self):
        self._check_supervisor()
        return self.line_ids.filtered(lambda line: line.state == "pending").action_copy_theoretical()

    def action_open_add_product_wizard(self):
        self._check_supervisor()
        self._check_capacity(self.wip_warehouse_ids)
        return super().action_open_add_product_wizard()

    def action_open_return_wizard(self):
        self._check_supervisor()
        self.ensure_one()
        if self.state not in ("pending_review", "pending_approval"):
            raise UserError(_("La sesión debe estar pendiente de revisión o aprobación."))
        return {"type": "ir.actions.act_window", "name": _("Devolver para reconteo"),
                "res_model": "sng.cycle.count.return.wizard", "view_mode": "form", "target": "new",
                "context": {"default_cycle_count_id": self.id}}

    def _close_overdue_activities(self):
        self.sudo().activity_search([OVERDUE_ACTIVITY]).action_feedback(feedback=_("Sesión resuelta."))
        self.sudo().activity_search(["sng_cycle_count.mail_activity_cycle_count_recount"]).action_feedback(
            feedback=_("Sesión resuelta."))

    @api.model
    def _cron_overdue_counts(self):
        counts = self.search([("state", "in", OPEN_STATES),
                              ("line_ids.is_overdue", "=", True)])
        activity_type = self.env.ref(OVERDUE_ACTIVITY)
        for count in counts:
            count._lock_sessions()
            if count.state not in OPEN_STATES or not any(count.line_ids.mapped("is_overdue")):
                continue
            for user in count.wip_warehouse_ids.cycle_supervisor_id.filtered("active"):
                existing = self.env["mail.activity"].sudo().search_count([
                    ("res_model", "=", self._name), ("res_id", "=", count.id),
                    ("activity_type_id", "=", activity_type.id), ("user_id", "=", user.id),
                ])
                if not existing:
                    count.activity_schedule(OVERDUE_ACTIVITY, user_id=user.id,
                                            summary=_("Resolver conteo vencido %s") % count.name)


class CycleCountConfigControl(models.Model):
    _inherit = "sng.cycle.count.config"

    def cron_generate_daily_counts(self):
        for config in self.search([("active", "=", True)]):
            quants = config._select_quants()
            for warehouse in quants.location_id.warehouse_id.sorted("id"):
                try:
                    with self.env.cr.savepoint():
                        selected = quants.filtered(lambda q: q.location_id.warehouse_id == warehouse)
                        self.env["sng.cycle.count"].create({
                            "config_id": config.id, "count_date": fields.Date.context_today(config),
                            "company_id": config.company_id.id, "warehouse_id": warehouse.id,
                            "user_id": config.user_id.id or False,
                            "line_ids": [fields.Command.create({"quant_id": q.id,
                                                                "theoretical_qty": q.quantity}) for q in selected],
                        })
                except UserError as error:
                    _logger.warning("No se generó conteo para bodega %s: %s", warehouse.display_name, error)
            if quants.filtered(lambda q: not q.location_id.warehouse_id):
                _logger.warning("Configuración %s: hay ubicaciones sin bodega física; no se programaron.", config.name)
        return True
