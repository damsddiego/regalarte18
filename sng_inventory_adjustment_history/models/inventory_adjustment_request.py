# -*- coding: utf-8 -*-

from psycopg2.errors import LockNotAvailable

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import email_split, float_compare


APPROVER_GROUP = (
    "sng_inventory_adjustment_history.group_inventory_adjustment_approver"
)


class InventoryAdjustmentRequest(models.Model):
    _name = "sng.inventory.adjustment.request"
    _description = "Solicitud de ajuste de inventario"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "product_id"
    _check_company_auto = True

    quant_id = fields.Many2one(
        "stock.quant", string="Existencia a contar", required=True,
        ondelete="restrict", check_company=True,
        domain="[('location_id.usage', 'in', ['internal', 'transit'])]",
    )
    product_id = fields.Many2one(related="quant_id.product_id", store=True)
    location_id = fields.Many2one(related="quant_id.location_id", store=True)
    warehouse_id = fields.Many2one(related="location_id.warehouse_id", store=True)
    lot_id = fields.Many2one(related="quant_id.lot_id")
    package_id = fields.Many2one(related="quant_id.package_id")
    owner_id = fields.Many2one(related="quant_id.owner_id")
    uom_id = fields.Many2one(related="product_id.uom_id")
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    previous_quantity = fields.Float(
        string="Cantidad anterior", readonly=True, digits="Product Unit of Measure",
    )
    counted_quantity = fields.Float(
        string="Conteo físico", required=True, digits="Product Unit of Measure",
        tracking=True,
    )
    difference_quantity = fields.Float(
        string="Unidades de discrepancia", compute="_compute_amounts", store=True,
        digits="Product Unit of Measure",
    )
    unit_cost = fields.Monetary(
        string="Costo unitario al registrar", readonly=True,
        groups="custom_ui_security.group_view_product_cost",
    )
    estimated_cost = fields.Monetary(
        string="Costo estimado del ajuste", compute="_compute_amounts", store=True,
        groups="custom_ui_security.group_view_product_cost",
        help="Estimación al registrar. El costo definitivo se obtiene al aplicar el ajuste.",
    )
    reason = fields.Text(string="Motivo justificado", required=True, tracking=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("pending", "Por aprobar"),
         ("approved", "Aprobado y aplicado"), ("rejected", "Rechazado")],
        default="draft", required=True, readonly=True, tracking=True, index=True,
    )
    requested_by_id = fields.Many2one(
        "res.users", string="Registrado por", required=True, readonly=True,
        default=lambda self: self.env.user,
    )
    submitted_at = fields.Datetime(string="Solicitado el", readonly=True)
    reviewed_by_id = fields.Many2one("res.users", string="Revisado por", readonly=True)
    reviewed_at = fields.Datetime(string="Revisado el", readonly=True)
    review_note = fields.Text(string="Motivo de rechazo / observación de Gerencia")
    move_ids = fields.One2many(
        "stock.move", "sng_adjustment_request_id", readonly=True,
        string="Movimientos aplicados",
    )
    history_ids = fields.One2many(
        "sng.inventory.adjustment.history", "request_id", readonly=True,
        string="Historial de ajustes",
    )

    def init(self):
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS sng_adjustment_request_pending_quant
            ON sng_inventory_adjustment_request (quant_id)
            WHERE state = 'pending'
        """)

    @api.depends("counted_quantity", "previous_quantity", "unit_cost")
    def _compute_amounts(self):
        for request in self:
            request.difference_quantity = request.counted_quantity - request.previous_quantity
            request.estimated_cost = request.difference_quantity * request.unit_cost

    @api.onchange("quant_id")
    def _onchange_quant_id(self):
        self.previous_quantity = self.quant_id.quantity
        self.company_id = self.quant_id.company_id or self.env.company

    @api.constrains("reason", "counted_quantity")
    def _check_count(self):
        for request in self:
            if not (request.reason or "").strip():
                raise ValidationError(_("Debe indicar el motivo justificado del ajuste."))
            if request.counted_quantity < 0:
                raise ValidationError(_("El conteo físico no puede ser negativo."))

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        prepared = []
        for vals in vals_list:
            if set(vals) - {"quant_id", "counted_quantity", "reason"}:
                raise AccessError(_("Solo puede registrar la existencia, el conteo y el motivo."))
            quant = self.env["stock.quant"].browse(vals.get("quant_id")).exists()
            if not quant or quant.location_id.usage not in ("internal", "transit"):
                raise ValidationError(_("Seleccione una existencia interna o en tránsito."))
            quant.check_access("write")
            prepared.append(dict(
                vals,
                company_id=quant.company_id.id or self.env.company.id,
                previous_quantity=quant.quantity,
                unit_cost=quant.sudo()._sng_get_adjustment_unit_cost(),
                requested_by_id=self.env.uid,
                state="draft",
                submitted_at=False,
                reviewed_by_id=False,
                reviewed_at=False,
                review_note=False,
            ))
        # Only the server-built snapshot uses sudo, so operators can register
        # requests without being allowed to read or supply product costs.
        return super(InventoryAdjustmentRequest, self.sudo()).create(prepared).with_env(self.env)

    def write(self, vals):
        protected = {
            "state", "quant_id", "company_id", "previous_quantity", "unit_cost",
            "requested_by_id", "submitted_at", "reviewed_by_id", "reviewed_at",
            "product_id", "location_id", "warehouse_id", "difference_quantity",
            "estimated_cost", "move_ids", "history_ids", "currency_id", "uom_id",
            "lot_id", "package_id", "owner_id",
        }
        if protected.intersection(vals):
            raise AccessError(_("Use las acciones de la solicitud para cambiar su estado."))
        if {"counted_quantity", "reason"}.intersection(vals):
            if any(request.state != "draft" for request in self):
                raise UserError(_("El conteo y el motivo solo pueden editarse en borrador."))
        if "review_note" in vals:
            self._check_approver()
            if any(request.state not in ("draft", "pending") for request in self):
                raise UserError(_("La revisión finalizada no puede modificarse."))
        return super().write(vals)

    def _check_approver(self):
        self.env["stock.quant"]._sng_check_inventory_approval_access()

    def _lock(self):
        self.check_access("write")
        self.flush_recordset()
        quants = self.quant_id
        quants.flush_recordset()
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    "SELECT id FROM sng_inventory_adjustment_request "
                    "WHERE id = ANY(%s) ORDER BY id FOR UPDATE NOWAIT", [self.ids],
                )
                self.env.cr.execute(
                    "SELECT id FROM stock_quant WHERE id = ANY(%s) "
                    "ORDER BY id FOR UPDATE NOWAIT", [quants.ids],
                )
        except LockNotAvailable as error:
            raise UserError(_("Otro proceso está revisando estas existencias. Intente nuevamente.")) from error
        self.invalidate_recordset()
        quants.invalidate_recordset()

    def _check_stock_unchanged(self):
        for request in self:
            if float_compare(
                request.quant_id.quantity, request.previous_quantity,
                precision_rounding=request.uom_id.rounding,
            ):
                raise UserError(_(
                    "Las existencias de %s cambiaron después del registro. "
                    "Rechace esta solicitud y registre un nuevo conteo."
                ) % request.product_id.display_name)

    def action_submit(self):
        self._lock()
        self._check_stock_unchanged()
        for request in self:
            if request.state != "draft":
                raise UserError(_("Solo puede enviar solicitudes en borrador."))
            duplicate = self.sudo().search_count([
                ("quant_id", "=", request.quant_id.id), ("state", "=", "pending"),
            ])
            if duplicate:
                raise UserError(_("Ya existe una solicitud por aprobar para esta existencia."))
            super(InventoryAdjustmentRequest, request).write({
                "state": "pending", "submitted_at": fields.Datetime.now(),
            })
            request._send_approval_notification()
        return True

    def action_approve(self):
        self._check_approver()
        self._lock()
        self._check_stock_unchanged()
        if any(request.state != "pending" for request in self):
            raise UserError(_("Solo puede aprobar solicitudes pendientes."))
        for request in self:
            request.quant_id.check_access("write")
            # Sudo is restricted to this private, authorized stock operation.
            # It also preserves compatibility with the independently approved cycle counts.
            quant = request.quant_id.sudo().with_context(
                inventory_mode=True,
                inventory_name=_("Solicitud de ajuste #%s: %s") % (request.id, request.reason),
                sng_adjustment_request_id=request.id,
            )
            quant.write({
                "inventory_quantity": request.counted_quantity,
                "user_id": request.requested_by_id.id,
            })
            quant._apply_inventory()
            super(InventoryAdjustmentRequest, request).write({
                "state": "approved", "reviewed_by_id": self.env.uid,
                "reviewed_at": fields.Datetime.now(),
            })
        return True

    def action_reject(self):
        self._check_approver()
        self._lock()
        for request in self:
            if request.state != "pending":
                raise UserError(_("Solo puede rechazar solicitudes pendientes."))
            if not (request.review_note or "").strip():
                raise UserError(_("Indique el motivo del rechazo en la observación de Gerencia."))
        return super().write({
            "state": "rejected", "reviewed_by_id": self.env.uid,
            "reviewed_at": fields.Datetime.now(),
        })

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
        body = self.env["ir.qweb"].sudo()._render(
            "sng_inventory_adjustment_history.mail_adjustment_approval_request",
            {"adjustment": self.sudo(), "url": url},
        )
        self.env["mail.mail"].sudo().create({
            "subject": _("Solicitud de aprobación de ajuste #%s: %s") % (
                self.id, self.product_id.display_name,
            ),
            "email_from": sender, "email_to": ",".join(dict.fromkeys(recipients)),
            "body_html": body, "auto_delete": False,
            "model": self._name, "res_id": self.id,
        })
