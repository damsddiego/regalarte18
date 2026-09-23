# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_is_zero

from .cycle_control import OPEN_STATES
from .cycle_count import SUPERVISOR_GROUP


class CycleCountCapture(models.Model):
    _name = "sng.cycle.count.capture"
    _description = "Auditoría de conteo y revisión"
    _order = "id desc"

    line_id = fields.Many2one("sng.cycle.count.line", required=True, ondelete="restrict")
    company_id = fields.Many2one(related="line_id.company_id", store=True)
    user_id = fields.Many2one("res.users", required=True)
    captured_at = fields.Datetime(required=True, default=fields.Datetime.now)
    quantity = fields.Float(string="Cantidad", digits="Product Unit of Measure")
    theoretical_qty = fields.Float(string="Teórico", digits="Product Unit of Measure")
    event = fields.Selection([("capture", "Captura"), ("review", "Visto bueno"),
                              ("recount", "Solicitar reconteo"), ("migration", "Migración")], required=True)
    reason = fields.Text(string="Motivo")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("La auditoría solo puede registrarla el servidor."))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("La auditoría es inmutable."))

    def unlink(self):
        raise AccessError(_("La auditoría es inmutable."))


class CycleCountLineControl(models.Model):
    _inherit = "sng.cycle.count.line"

    cycle_state = fields.Selection(related="cycle_count_id.state", string="Estado de la sesión")

    def action_open_control(self):
        self.ensure_one()
        self.check_access("read")
        return {"type": "ir.actions.act_window", "name": _("Revisión de línea cíclica"),
                "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "current"}

    first_difference_at = fields.Datetime(string="Primera diferencia", readonly=True, copy=False)
    warning_at = fields.Datetime(string="Inicio de advertencia", readonly=True, copy=False)
    deadline_at = fields.Datetime(string="Vence el", readonly=True, copy=False, index=True)
    counted_by_ids = fields.Many2many("res.users", "sng_cycle_line_counter_rel", "line_id", "user_id",
                                     string="Participantes del conteo", readonly=True, copy=False)
    last_counted_by_id = fields.Many2one("res.users", string="Último conteo por", readonly=True, copy=False)
    capture_ids = fields.One2many("sng.cycle.count.capture", "line_id", string="Auditoría", readonly=True)
    review_state = fields.Selection([
        ("capture", "Captura"), ("review", "Requiere revisión"),
        ("recount", "Requiere reconteo"), ("approved", "Visto bueno de Jefatura"),
    ], default="capture", readonly=True, copy=False, string="Revisión")
    review_reason = fields.Text(string="Justificación de Jefatura", copy=False)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False, string="Revisado por")
    reviewed_at = fields.Datetime(readonly=True, copy=False, string="Revisado el")
    applied_by_id = fields.Many2one("res.users", readonly=True, copy=False, string="Aplicado por")
    applied_at = fields.Datetime(readonly=True, copy=False, string="Aplicado el")
    unresolved = fields.Boolean(compute="_compute_unresolved", store=True, index=True)
    is_overdue = fields.Boolean(string="Vencido", compute="_compute_alerts", search="_search_overdue")
    is_warning = fields.Boolean(string="Próximo a vencer", compute="_compute_alerts", search="_search_warning")

    @api.depends("first_difference_at", "state", "cycle_count_id.state")
    def _compute_unresolved(self):
        for line in self:
            line.unresolved = bool(line.first_difference_at and line.state not in ("adjusted", "cancelled")
                                   and line.cycle_count_id.state in OPEN_STATES)

    @api.depends("unresolved", "deadline_at", "warning_at")
    def _compute_alerts(self):
        now = fields.Datetime.now()
        for line in self:
            line.is_overdue = bool(line.unresolved and line.deadline_at and now > line.deadline_at)
            line.is_warning = bool(line.unresolved and line.warning_at and line.deadline_at
                                   and line.warning_at <= now <= line.deadline_at)

    def _alert_domain(self, warning=False):
        now = fields.Datetime.now()
        domain = [("unresolved", "=", True), ("deadline_at", "<", now)]
        if warning:
            domain = [("unresolved", "=", True), ("warning_at", "<=", now), ("deadline_at", ">=", now)]
        return domain

    def _search_overdue(self, operator, value):
        domain = self._alert_domain()
        return domain if (operator == "=") == bool(value) else expression.NOT(domain)

    def _search_warning(self, operator, value):
        domain = self._alert_domain(warning=True)
        return domain if (operator == "=") == bool(value) else expression.NOT(domain)

    def _control_write(self, vals):
        return super(CycleCountLineControl, self.sudo()).write(vals)

    def _audit(self, event, reason=False):
        self.env["sng.cycle.count.capture"].sudo().create([
            {"line_id": line.id, "user_id": self.env.uid, "captured_at": fields.Datetime.now(),
             "quantity": line.counted_qty, "theoretical_qty": line.theoretical_qty,
             "event": event, "reason": reason or line.notes}
            for line in self
        ])

    def _check_independent_reviewer(self):
        self.check_access("read")
        if any(self.env.user in line.counted_by_ids for line in self):
            raise AccessError(_("Quien contó o recontó no puede revisar ni aplicar ese mismo ajuste."))
        if any(not line.counted_by_ids for line in self):
            raise UserError(_("Falta identificar al capturador; registre un nuevo conteo antes de aprobar."))

    @api.model_create_multi
    def create(self, vals_list):
        self.env["sng.cycle.count"]._check_supervisor()
        records = self.browse()
        with self.env.cr.savepoint():
            for original in vals_list:
                vals = dict(original)
                count = self.env["sng.cycle.count"].browse(vals.get("cycle_count_id"))
                count.check_access("write")
                count._check_capacity(count.wip_warehouse_ids)
                count._lock_sessions()
                if count.state not in ("draft", "in_progress"):
                    raise UserError(_("No puede agregar líneas a una sesión en revisión o finalizada."))
                quant = self.env["stock.quant"].browse(vals.get("quant_id")).exists()
                quant.check_access("read")
                if not quant or quant.location_id.warehouse_id != count.warehouse_id:
                    raise ValidationError(_("El producto debe pertenecer a la bodega física de la sesión."))
                quant._cycle_lock()
                if quant.sng_cycle_line_id:
                    raise ValidationError(_("Esta existencia ya pertenece a otro conteo abierto."))
                if quant.inventory_quantity_set or self.env["sng.inventory.adjustment.request"].sudo().search_count([
                    ("quant_id", "=", quant.id), ("state", "in", ["draft", "pending"]),
                ]):
                    raise UserError(_("Resuelva el conteo o la solicitud manual pendiente de esta existencia."))
                allowed = {"cycle_count_id", "quant_id", "theoretical_qty", "counted_qty", "notes", "is_manual"}
                if not self.env.su and set(vals) - allowed:
                    raise AccessError(_("No puede proporcionar estados ni auditoría al crear una línea."))
                quantity = vals.pop("counted_qty", None)
                vals.update(theoretical_qty=quant.quantity, state="pending")
                line = super().create([vals])
                quant.sudo().write({"sng_cycle_line_id": line.id})
                if quantity is not None:
                    line.write({"counted_qty": quantity})
                records |= line
        return records

    def write(self, vals):
        if self.env.su:
            # Server maintenance (cost refresh, final state) keeps original guards.
            if "counted_qty" not in vals:
                return super().write(vals)
        else:
            allowed = {"counted_qty", "notes", "review_reason"}
            if set(vals) - allowed:
                raise AccessError(_("Solo puede editar cantidad contada, observaciones o el motivo de revisión."))
            self.check_access("write")
        counts = self.cycle_count_id
        counts._lock_warehouses(counts.wip_warehouse_ids)
        counts._lock_sessions()
        self.invalidate_recordset()
        if "review_reason" in vals:
            counts._check_supervisor()
            if any(l.state in ("adjusted", "cancelled") or l.cycle_count_id.state not in OPEN_STATES for l in self):
                raise UserError(_("La revisión finalizada es inmutable."))
            if any(l.review_state == "approved" for l in self):
                raise UserError(_("El motivo del visto bueno es inmutable; solicite un reconteo para revisarlo."))
        if {"counted_qty", "notes"}.intersection(vals):
            if any(l.cycle_count_id.state not in ("draft", "in_progress") or l.state in ("adjusted", "cancelled") for l in self):
                raise UserError(_("Devuelva la línea para reconteo antes de modificarla."))
        for line in self:
            values = dict(vals)
            if "counted_qty" in vals:
                if vals["counted_qty"] < 0:
                    raise ValidationError(_("La cantidad contada no puede ser negativa."))
                if not line.cycle_count_id.wip_started:
                    line.cycle_count_id.action_start()
                now = fields.Datetime.now()
                different = not float_is_zero(vals["counted_qty"] - line.theoretical_qty,
                                               precision_rounding=line.product_uom_id.rounding)
                values.update(state="counted", count_date=now, last_counted_by_id=self.env.uid,
                              counted_by_ids=[fields.Command.link(self.env.uid)],
                              review_state="review", reviewed_by_id=False, reviewed_at=False, review_reason=False)
                if different and not line.first_difference_at:
                    warning, deadline = line.quant_id.location_id.warehouse_id._cycle_deadlines(now)
                    values.update(first_difference_at=now, warning_at=warning, deadline_at=deadline)
            line._control_write(values)
            if "counted_qty" in vals:
                line._audit("capture")
                line._sync_quant()
            elif "notes" in vals:
                line.quant_id.sudo().write({"sng_adjustment_reason": line.notes})
        return True

    def _sync_quant(self):
        for line in self:
            # Private projection: no second capture and no application to stock.
            line.quant_id.sudo().write({"inventory_quantity": line.counted_qty,
                                       "user_id": line.last_counted_by_id.id,
                                       "sng_adjustment_reason": line.notes or False})

    def _release_quants(self):
        for line in self:
            if line.quant_id.sng_cycle_line_id == line:
                line.quant_id.sudo().write({"sng_cycle_line_id": False})
                line.quant_id.sudo().action_clear_inventory_quantity()

    def _send_for_review(self):
        if any(l.state != "counted" for l in self):
            raise UserError(_("Registre la cantidad antes de enviarla a revisión."))
        self.filtered(lambda l: l.review_state != "approved")._control_write({"review_state": "review"})

    def action_send_for_review(self):
        self.check_access("write")
        self.cycle_count_id._lock_sessions()
        if any(line.cycle_count_id.state not in ("draft", "in_progress") for line in self):
            raise UserError(_("La línea debe estar en una sesión en captura."))
        self._send_for_review()
        # The inventory list is a complete entry point: the last submitted line
        # advances the session without requiring a second visit to its form.
        for count in self.cycle_count_id:
            if count.line_ids and all(line.state == "counted" for line in count.line_ids):
                count.action_submit_for_approval()
        return True

    def action_review_approve(self):
        self.cycle_count_id._check_supervisor()
        self.cycle_count_id._lock_sessions()
        self._check_independent_reviewer()
        for line in self:
            if line.state != "counted" or line.review_state != "review" or line.cycle_count_id.state not in OPEN_STATES:
                raise UserError(_("La línea debe estar contada y pendiente de revisión."))
            if not (line.review_reason or "").strip():
                raise UserError(_("Indique la justificación de Jefatura para dar el visto bueno."))
            line._control_write({"review_state": "approved", "reviewed_by_id": self.env.uid,
                                 "reviewed_at": fields.Datetime.now()})
            line._audit("review", line.review_reason)
        return True

    def action_request_recount(self):
        self.cycle_count_id._check_supervisor()
        self.cycle_count_id._lock_sessions()
        self._check_independent_reviewer()
        for line in self:
            if not (line.review_reason or "").strip():
                raise UserError(_("Indique el motivo del reconteo."))
            line._return_for_recount(line.review_reason)
        return True

    def _return_for_recount(self, reason):
        for line in self:
            if line.cycle_count_id.state not in OPEN_STATES or line.state in ("adjusted", "cancelled"):
                raise UserError(_("No puede devolver una línea finalizada."))
            line.cycle_count_id._lock_quants()
            line._audit("recount", reason)
            line._control_write({"previous_theoretical_qty": line.theoretical_qty,
                                 "previous_counted_qty": line.counted_qty,
                                 "theoretical_qty": line.quant_id.quantity, "state": "pending",
                                 "review_state": "recount", "reviewed_by_id": False, "reviewed_at": False,
                                 "review_reason": reason})
            line.cycle_count_id._system_write({"state": "in_progress"})
            line.cycle_count_id._close_management_activities(_("Reconteo solicitado."))
            line.cycle_count_id._notify_operator_recount(reason, self.browse())

    @api.onchange("counted_qty")
    def _onchange_counted_qty(self):
        # State, timestamps and participants are set by write(), including RPC/import.
        pass

    def action_set_counted(self):
        for line in self:
            line.write({"counted_qty": line.counted_qty})
        return True

    def action_copy_theoretical(self):
        self.cycle_count_id._check_supervisor()
        for line in self:
            line.write({"counted_qty": line.theoretical_qty})
        return True

    def unlink(self):
        self.cycle_count_id._check_supervisor()
        if any(l.capture_ids or l.cycle_count_id.wip_started for l in self):
            raise UserError(_("No puede eliminar líneas de una sesión asignada o con historial."))
        self.quant_id.sudo().write({"sng_cycle_line_id": False})
        return super().unlink()
