# -*- coding: utf-8 -*-

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_split


APPROVER_GROUP = (
    "sng_inventory_adjustment_history.group_inventory_adjustment_approver"
)


class InventoryAdjustmentBatch(models.Model):
    """Cabecera de una solicitud de ajuste: una bodega (ubicación interna) y
    varias líneas, cada una con una existencia, su conteo y su motivo."""

    _name = "sng.inventory.adjustment.batch"
    _description = "Solicitud de ajuste de inventario"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    location_id = fields.Many2one(
        "stock.location", string="Bodega", required=True, check_company=True,
        domain="[('usage', 'in', ['internal', 'transit'])]", tracking=True,
    )
    warehouse_id = fields.Many2one(related="location_id.warehouse_id", store=True)
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_ids = fields.One2many(
        "sng.inventory.adjustment.request", "batch_id", string="Líneas", copy=False,
    )
    line_count = fields.Integer(compute="_compute_line_count")
    state = fields.Selection(
        [("draft", "Borrador"), ("pending", "Por aprobar"),
         ("approved", "Aprobado y aplicado"), ("rejected", "Rechazado")],
        compute="_compute_state", store=True, readonly=True, index=True, tracking=True,
    )
    estimated_cost = fields.Monetary(
        string="Costo estimado del ajuste", compute="_compute_estimated_cost",
        compute_sudo=True, groups="custom_ui_security.group_view_product_cost",
    )
    requested_by_id = fields.Many2one(
        "res.users", string="Registrado por", required=True, readonly=True,
        default=lambda self: self.env.user,
    )
    submitted_at = fields.Datetime(string="Solicitado el", readonly=True)
    recalculated_at = fields.Datetime(string="Existencias recalculadas el", readonly=True)
    reviewed_by_id = fields.Many2one("res.users", string="Revisado por", readonly=True)
    reviewed_at = fields.Datetime(string="Revisado el", readonly=True)
    review_note = fields.Text(string="Motivo de rechazo / observación de Gerencia")
    history_ids = fields.One2many(
        "sng.inventory.adjustment.history", "batch_id", readonly=True,
        string="Historial de ajustes",
    )

    @api.depends("location_id")
    def _compute_display_name(self):
        for batch in self:
            name = _("Solicitud de ajuste #%s") % (batch.id or "")
            if batch.location_id:
                name = "%s - %s" % (name, batch.location_id.display_name)
            batch.display_name = name

    @api.depends("line_ids")
    def _compute_line_count(self):
        for batch in self:
            batch.line_count = len(batch.line_ids)

    @api.depends("line_ids.state")
    def _compute_state(self):
        for batch in self:
            states = set(batch.line_ids.mapped("state"))
            if not states or "draft" in states:
                batch.state = "draft"
            elif "pending" in states:
                batch.state = "pending"
            elif "approved" in states:
                batch.state = "approved"
            else:
                batch.state = "rejected"

    @api.depends("line_ids.estimated_cost")
    def _compute_estimated_cost(self):
        for batch in self:
            batch.estimated_cost = sum(batch.line_ids.mapped("estimated_cost"))

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        allowed = {"location_id", "line_ids"}
        prepared = []
        for vals in vals_list:
            vals = {
                field: value for field, value in vals.items()
                if field in allowed or value not in (False, None, "", [], 0, 0.0)
            }
            if set(vals) - allowed:
                raise AccessError(_("Solo puede registrar la bodega y las líneas de la solicitud."))
            location = self.env["stock.location"].browse(vals.get("location_id")).exists()
            if not location or location.usage not in ("internal", "transit"):
                raise UserError(_("Seleccione una bodega interna o en tránsito."))
            prepared.append(dict(
                vals,
                company_id=location.company_id.id or self.env.company.id,
                requested_by_id=self.env.uid,
            ))
        return super().create(prepared)

    def write(self, vals):
        protected = {
            "state", "company_id", "warehouse_id", "currency_id", "requested_by_id",
            "submitted_at", "recalculated_at", "reviewed_by_id", "reviewed_at", "history_ids",
        }
        if protected.intersection(vals):
            raise AccessError(_("Use las acciones de la solicitud para cambiar su estado."))
        if "location_id" in vals:
            if any(batch.line_ids and batch.location_id.id != vals["location_id"] for batch in self):
                raise UserError(_("Elimine las líneas antes de cambiar la bodega de la solicitud."))
        if "line_ids" in vals and any(batch.state != "draft" for batch in self):
            # Gerencia edita observaciones de líneas desde la cabecera (comando 1);
            # agregar, quitar o reemplazar líneas requiere borrador.
            if any(command[0] != 1 for command in vals["line_ids"]):
                raise UserError(_("Solo se pueden agregar o quitar líneas en borrador."))
        if "review_note" in vals:
            self._check_approver()
            if any(batch.state not in ("draft", "pending") for batch in self):
                raise UserError(_("La revisión finalizada no puede modificarse."))
        return super().write(vals)

    def unlink(self):
        self.check_access("unlink")
        if any(batch.state != "draft" for batch in self):
            raise UserError(_("Solo se pueden eliminar solicitudes en borrador."))
        return super().unlink()

    def _system_write(self, vals):
        return super(InventoryAdjustmentBatch, self).write(vals)

    def _check_approver(self):
        self.env["stock.quant"]._sng_check_inventory_approval_access()

    def _pending_lines(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.state == "pending")
        if not lines:
            raise UserError(_("La solicitud no tiene líneas pendientes de aprobación."))
        return lines

    def action_submit(self):
        for batch in self:
            if batch.state != "draft":
                raise UserError(_("Solo puede enviar solicitudes en borrador."))
            lines = batch.line_ids.filtered(lambda line: line.state == "draft")
            if not lines:
                raise UserError(_("Agregue al menos una línea con el conteo físico."))
            lines.action_submit()
            batch._system_write({"submitted_at": fields.Datetime.now()})
            batch._send_approval_notification()
        return True

    def action_approve(self):
        self._check_approver()
        for batch in self:
            batch._pending_lines().action_approve()
            batch._system_write({
                "reviewed_by_id": self.env.uid, "reviewed_at": fields.Datetime.now(),
            })
        return True

    def action_recalculate(self):
        """Refresca existencia actual y cantidad resultante de las líneas pendientes
        y deja en el chatter las líneas cuyo stock cambió desde el conteo. No toca
        el conteo registrado."""
        self._check_approver()
        for batch in self:
            lines = batch._pending_lines()
            lines.quant_id.invalidate_recordset(["quantity"])
            lines.invalidate_recordset(["current_quantity", "result_quantity", "stock_changed"])
            changed = lines.filtered("stock_changed")
            batch._system_write({"recalculated_at": fields.Datetime.now()})
            if changed:
                rows = Markup("").join(
                    Markup("<li>%s: al contar %s, conteo %s, hoy %s, resultante <b>%s</b></li>") % (
                        escape(line.product_id.display_name),
                        line.previous_quantity, line.counted_quantity,
                        line.current_quantity, line.result_quantity,
                    ) for line in changed
                )
                body = Markup("<p>%s</p><ul>%s</ul>") % (
                    _("Existencias recalculadas: %(count)s de %(total)s líneas cambiaron desde el conteo. "
                      "Al aprobar se aplica la diferencia del conteo sobre la existencia actual.",
                      count=len(changed), total=len(lines)),
                    rows,
                )
            else:
                body = Markup("<p>%s</p>") % _(
                    "Existencias recalculadas: ninguna línea cambió desde el conteo."
                )
            batch.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note")
        return True

    def action_reject(self):
        self._check_approver()
        for batch in self:
            lines = batch._pending_lines()
            if not (batch.review_note or "").strip():
                raise UserError(_("Indique el motivo del rechazo en la observación de Gerencia."))
            lines.write({"review_note": batch.review_note})
            lines.action_reject()
            batch._system_write({
                "reviewed_by_id": self.env.uid, "reviewed_at": fields.Datetime.now(),
            })
        return True

    def _send_approval_notification(self):
        self.ensure_one()
        groups = self.env["sng.warehouse.group"].sudo().search([
            ("warehouse_ids", "in", self.warehouse_id.ids),
        ]) if self.warehouse_id else self.env["sng.warehouse.group"]
        recipients = []
        for group in groups:
            recipients.extend(email_split(
                group.adjustment_approval_emails or group.adjustment_notify_emails or ""
            ))
        if not recipients:
            managers = self.env.ref(APPROVER_GROUP).sudo().users.filtered(
                lambda user: user.active and not user.share and self.company_id in user.company_ids
            )
            for manager in managers:
                recipients.extend(email_split(manager.email or ""))
        if not recipients:
            raise UserError(_(
                "Configure los correos de Gerencia en el grupo de almacenes "
                "o asigne un usuario aprobador con correo electrónico."
            ))
        sender = next(iter(groups.filtered("adjustment_sender_email").mapped(
            "adjustment_sender_email"
        )), False) or self.company_id.email_formatted or self.env.user.email_formatted
        url = "%s/web#id=%s&model=%s&view_type=form" % (
            self.get_base_url(), self.id, self._name,
        )
        batch = self.sudo()
        body = self.env["ir.qweb"].sudo()._render(
            "sng_inventory_adjustment_history.mail_adjustment_approval_request",
            {"batch": batch, "lines": batch.line_ids.filtered(lambda l: l.state == "pending"), "url": url},
        )
        self.env["mail.mail"].sudo().create({
            "subject": _("Solicitud de aprobación de ajuste #%s: %s") % (
                self.id, self.location_id.display_name,
            ),
            "email_from": sender, "email_to": ",".join(dict.fromkeys(recipients)),
            "body_html": body, "auto_delete": False,
            "model": self._name, "res_id": self.id,
        })
