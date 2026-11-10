# -*- coding: utf-8 -*-

from psycopg2.errors import LockNotAvailable

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare


APPROVER_GROUP = (
    "sng_inventory_adjustment_history.group_inventory_adjustment_approver"
)


class InventoryAdjustmentRequest(models.Model):
    """Línea de una solicitud de ajuste: una existencia (quant) con su conteo
    físico y su motivo. La cabecera es ``sng.inventory.adjustment.batch``.

    Otros módulos (``sng_cycle_count``, ``sng_inventario_movil``) consultan
    este modelo por ``quant_id`` y ``state``; esa interfaz se conserva.
    """

    _name = "sng.inventory.adjustment.request"
    _description = "Línea de solicitud de ajuste de inventario"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id"
    _rec_name = "product_id"
    _check_company_auto = True

    batch_id = fields.Many2one(
        "sng.inventory.adjustment.batch", string="Solicitud", required=True,
        ondelete="cascade", index=True, check_company=True, readonly=True,
    )
    quant_id = fields.Many2one(
        "stock.quant", string="Existencia a contar", readonly=True,
        ondelete="restrict", check_company=True, index=True,
        domain="[('location_id.usage', 'in', ['internal', 'transit'])]",
    )
    product_id = fields.Many2one(
        "product.product", string="Producto", required=True, check_company=True,
        domain="[('is_storable', '=', True)]",
    )
    lot_id = fields.Many2one(
        "stock.lot", string="Lote/Serie", check_company=True,
        domain="[('product_id', '=', product_id)]",
    )
    location_id = fields.Many2one(related="quant_id.location_id", store=True)
    warehouse_id = fields.Many2one(related="location_id.warehouse_id", store=True)
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
    current_quantity = fields.Float(
        string="Existencia actual", compute="_compute_current_figures",
        digits="Product Unit of Measure",
        help="Cantidad del sistema en este momento. Puede diferir de la cantidad al "
             "contar si hubo movimientos después del conteo.",
    )
    result_quantity = fields.Float(
        string="Cantidad resultante", compute="_compute_current_figures",
        digits="Product Unit of Measure",
        help="Existencia actual más la discrepancia del conteo. Es la cantidad que "
             "quedará al aprobar.",
    )
    stock_changed = fields.Boolean(
        string="Stock cambió desde el conteo", compute="_compute_current_figures",
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
    counted_by_ids = fields.Many2many(
        "res.users", "sng_request_counter_rel", "request_id", "user_id",
        string="Participantes del conteo", readonly=True, copy=False,
    )
    last_counted_by_id = fields.Many2one("res.users", string="Último capturador", readonly=True, copy=False)
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

    @api.depends("quant_id.quantity", "previous_quantity", "difference_quantity", "state")
    def _compute_current_figures(self):
        for request in self:
            current = request.quant_id.quantity if request.quant_id else 0.0
            request.current_quantity = current
            request.result_quantity = current + request.difference_quantity
            request.stock_changed = request.state in ("draft", "pending") and bool(float_compare(
                current, request.previous_quantity,
                precision_rounding=request.uom_id.rounding or 0.01,
            ))

    @api.onchange("quant_id")
    def _onchange_quant_id(self):
        if self.quant_id:
            self.product_id = self.quant_id.product_id
            self.lot_id = self.quant_id.lot_id
            self.previous_quantity = self.quant_id.quantity
            self.company_id = self.quant_id.company_id or self.env.company

    @api.onchange("product_id", "lot_id")
    def _onchange_product_id(self):
        """Muestra la cantidad actual del producto en la bodega de la cabecera.
        Si no hay existencia, la cantidad anterior es 0 y el servidor la crea al guardar."""
        location = self.batch_id.location_id
        quant = self.env["stock.quant"]
        if self.product_id and location:
            quant = quant._sng_find_quant(self.product_id, location, self.lot_id)
        self.quant_id = quant
        self.previous_quantity = quant.quantity if quant else 0.0

    @api.constrains("reason", "counted_quantity")
    def _check_count(self):
        for request in self:
            if not (request.reason or "").strip():
                raise ValidationError(_("Debe indicar el motivo justificado del ajuste."))
            if request.counted_quantity < 0:
                raise ValidationError(_("El conteo físico no puede ser negativo."))

    @api.constrains("batch_id", "quant_id", "product_id")
    def _check_batch_consistency(self):
        for request in self:
            if not request.quant_id:
                raise ValidationError(_("No se pudo determinar la existencia de %s.") % request.product_id.display_name)
            if request.quant_id.product_id != request.product_id:
                raise ValidationError(_("La existencia no corresponde al producto %s.") % request.product_id.display_name)
            if request.quant_id.location_id != request.batch_id.location_id:
                raise ValidationError(_(
                    "El producto %(product)s está en %(location)s y la solicitud es de la bodega %(batch)s.",
                    product=request.product_id.display_name,
                    location=request.quant_id.location_id.complete_name,
                    batch=request.batch_id.location_id.complete_name,
                ))
            if self.sudo().search_count([
                ("batch_id", "=", request.batch_id.id), ("quant_id", "=", request.quant_id.id),
                ("id", "!=", request.id),
            ]):
                raise ValidationError(_("El producto %s ya está en otra línea de esta solicitud.") % request.product_id.display_name)

    @api.model
    def _sng_resolve_quant_vals(self, vals_list):
        """Completa ``quant_id`` en cada diccionario a partir de la bodega de la
        cabecera y el producto (y lote). Modifica los diccionarios en sitio para
        que los módulos que heredan ``create`` puedan bloquear la existencia
        antes de llamar a ``super()``."""
        Batch = self.env["sng.inventory.adjustment.batch"]
        Quant = self.env["stock.quant"]
        for vals in vals_list:
            batch = Batch.browse(vals.get("batch_id")).exists()
            if not batch:
                raise ValidationError(_("La línea debe pertenecer a una solicitud de ajuste."))
            if batch.state != "draft":
                raise UserError(_("Solo se pueden agregar líneas a una solicitud en borrador."))
            quant = Quant.browse(vals.get("quant_id")).exists()
            if not quant:
                product = self.env["product.product"].browse(vals.get("product_id")).exists()
                if not product:
                    raise ValidationError(_("Seleccione el producto de la línea."))
                lot = self.env["stock.lot"].browse(vals.get("lot_id")).exists()
                quant = Quant._sng_find_or_create_quant(product, batch.location_id, lot)
                vals["quant_id"] = quant.id
            elif vals.get("product_id") and vals["product_id"] != quant.product_id.id:
                raise ValidationError(_("La existencia seleccionada no corresponde al producto."))
            if quant.location_id != batch.location_id:
                raise ValidationError(_(
                    "El producto %(product)s está en %(location)s y la solicitud es de la bodega %(batch)s.",
                    product=quant.product_id.display_name,
                    location=quant.location_id.complete_name,
                    batch=batch.location_id.complete_name,
                ))
            vals["product_id"] = quant.product_id.id
            vals["lot_id"] = quant.lot_id.id

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        allowed = {"batch_id", "quant_id", "product_id", "lot_id", "counted_quantity", "reason"}
        cleaned = []
        for vals in vals_list:
            # El formulario envía vacíos los demás campos editables de la vista
            # (p. ej. review_note para Gerencia); solo se rechaza un valor real.
            vals = {
                field: value for field, value in vals.items()
                if field in allowed or value not in (False, None, "", [], 0, 0.0)
            }
            if set(vals) - allowed:
                raise AccessError(_("Solo puede registrar el producto, el conteo y el motivo."))
            cleaned.append(vals)
        self._sng_resolve_quant_vals(cleaned)
        prepared = []
        for vals in cleaned:
            quant = self.env["stock.quant"].browse(vals["quant_id"])
            if quant.location_id.usage not in ("internal", "transit"):
                raise ValidationError(_("Seleccione una existencia interna o en tránsito."))
            quant.check_access("write")
            prepared.append(dict(
                vals,
                company_id=quant.company_id.id or self.env.company.id,
                previous_quantity=quant.quantity,
                unit_cost=quant.sudo()._sng_get_adjustment_unit_cost(),
                requested_by_id=self.env.uid,
                counted_by_ids=[fields.Command.set((quant.sng_counted_by_ids | self.env.user).ids)],
                last_counted_by_id=self.env.uid,
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
            "state", "quant_id", "batch_id", "company_id", "previous_quantity", "unit_cost",
            "requested_by_id", "submitted_at", "reviewed_by_id", "reviewed_at",
            "location_id", "warehouse_id", "difference_quantity",
            "estimated_cost", "move_ids", "history_ids", "currency_id", "uom_id",
            "package_id", "owner_id",
            "counted_by_ids", "last_counted_by_id",
        }
        if protected.intersection(vals):
            raise AccessError(_("Use las acciones de la solicitud para cambiar su estado."))
        editable = {"counted_quantity", "reason", "product_id", "lot_id"}
        if editable.intersection(vals):
            if any(request.state != "draft" for request in self):
                raise UserError(_("El conteo y el motivo solo pueden editarse en borrador."))
        if "review_note" in vals:
            self._check_approver()
            if any(request.state not in ("draft", "pending") for request in self):
                raise UserError(_("La revisión finalizada no puede modificarse."))
        if {"product_id", "lot_id"}.intersection(vals):
            self._sng_change_product(vals.get("product_id"), vals.get("lot_id"))
            vals = {field: value for field, value in vals.items() if field not in ("product_id", "lot_id")}
        result = super().write(vals) if vals else True
        if "counted_quantity" in vals:
            super(InventoryAdjustmentRequest, self.sudo()).write({
                "counted_by_ids": [fields.Command.link(self.env.uid)],
                "last_counted_by_id": self.env.uid,
            })
        return result

    def _sng_change_product(self, product_id, lot_id):
        """Cambio de producto o lote en borrador: vuelve a resolver la existencia
        y refresca la foto de cantidad y costo."""
        for request in self:
            resolved = {
                "batch_id": request.batch_id.id,
                "product_id": product_id or request.product_id.id,
                "lot_id": lot_id if lot_id is not None else request.lot_id.id,
            }
            self._sng_resolve_quant_vals([resolved])
            quant = self.env["stock.quant"].browse(resolved["quant_id"])
            quant.check_access("write")
            super(InventoryAdjustmentRequest, request.sudo()).write({
                "quant_id": quant.id,
                "product_id": quant.product_id.id,
                "lot_id": quant.lot_id.id,
                "company_id": quant.company_id.id or self.env.company.id,
                "previous_quantity": quant.quantity,
                "unit_cost": quant.sudo()._sng_get_adjustment_unit_cost(),
            })

    def unlink(self):
        self.check_access("unlink")
        if any(request.state != "draft" for request in self):
            raise UserError(_("Solo se pueden eliminar líneas en borrador."))
        return super().unlink()

    @api.model
    def _create_from_quants(self, quants):
        """Agrupa las existencias por ubicación en una solicitud por bodega.
        Conserva a los capturadores reales aunque otro usuario envíe la solicitud."""
        quants.check_access("write")
        for quant in quants:
            if not quant.sng_counted_by_ids:
                raise UserError(_("Registre nuevamente la cantidad para identificar al capturador."))
        batches = self.env["sng.inventory.adjustment.batch"]
        for location in quants.location_id:
            location_quants = quants.filtered(lambda q: q.location_id == location).sorted("id")
            batch = batches.create({
                "location_id": location.id,
                "line_ids": [fields.Command.create({
                    "quant_id": quant.id,
                    "counted_quantity": quant.inventory_quantity,
                    "reason": quant.sng_adjustment_reason,
                }) for quant in location_quants],
            })
            for line in batch.line_ids:
                super(InventoryAdjustmentRequest, line.sudo()).write({
                    "counted_by_ids": [fields.Command.set(line.quant_id.sng_counted_by_ids.ids)],
                    "last_counted_by_id": line.quant_id.sng_last_counted_by_id.id,
                })
            batches |= batch
        return batches

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

    def _check_result_not_negative(self):
        """El ajuste se aplica por diferencia sobre la existencia actual; si el
        faltante detectado supera lo que queda hoy, la línea debe rechazarse."""
        for request in self:
            rounding = request.uom_id.rounding or 0.01
            if float_compare(request.result_quantity, 0.0, precision_rounding=rounding) < 0:
                raise UserError(_(
                    "La existencia actual de %(product)s es %(current)s y el conteo detectó un "
                    "faltante de %(missing)s, así que el ajuste dejaría %(result)s. "
                    "Rechace esta línea y registre un nuevo conteo; el resto de la "
                    "solicitud se puede aprobar.",
                    product=request.product_id.display_name,
                    current=request.current_quantity,
                    missing=abs(request.difference_quantity),
                    result=request.result_quantity,
                ))

    def action_submit(self):
        """Pasa las líneas a Por aprobar. El correo a Gerencia lo envía la cabecera."""
        self._lock()
        for request in self:
            if request.state != "draft":
                raise UserError(_("Solo puede enviar solicitudes en borrador."))
            duplicate = self.sudo().search_count([
                ("quant_id", "=", request.quant_id.id), ("state", "=", "pending"),
            ])
            if duplicate:
                raise UserError(_("Ya existe una solicitud por aprobar para %s.") % request.product_id.display_name)
            super(InventoryAdjustmentRequest, request).write({
                "state": "pending", "submitted_at": fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        self._check_approver()
        self._lock()
        if any(self.env.user in (request.counted_by_ids or request.requested_by_id) for request in self):
            raise AccessError(_("Quien contó o recontó no puede aprobar ese mismo ajuste."))
        if any(request.state != "pending" for request in self):
            raise UserError(_("Solo puede aprobar solicitudes pendientes."))
        # Con las existencias bloqueadas, la cantidad resultante se calcula sobre
        # el stock real de este instante: conteo − cantidad al contar + existencia actual.
        self._check_result_not_negative()
        for request in self:
            request.quant_id.check_access("write")
            # Sudo is restricted to this private, authorized stock operation.
            # It also preserves compatibility with the independently approved cycle counts.
            quant = request.quant_id.sudo().with_context(
                inventory_mode=True,
                inventory_name=_("Solicitud de ajuste #%s: %s") % (request.batch_id.id, request.reason),
                sng_adjustment_request_id=request.id,
            )
            quant.write({
                "inventory_quantity": request.result_quantity,
                "user_id": request.last_counted_by_id.id or request.requested_by_id.id,
                "sng_last_counted_by_id": request.last_counted_by_id.id or request.requested_by_id.id,
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

    def action_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "view_mode": "form", "target": "current",
        }