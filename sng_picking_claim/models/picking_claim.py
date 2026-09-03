# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Modelos que la app puede reclamar. Se valida contra esta lista blanca antes
# de construir cualquier consulta, porque el nombre de la tabla se interpola en
# el SQL del bloqueo.
SOURCE_MODELS = ("sale.order", "stock.picking")

ROLES = [
    ("bodega", "Bodega"),
    ("revision", "Revisión"),
    ("cedi", "CEDI / Relleno"),
]

RELEASE_REASONS = [
    ("done", "Etapa completada"),
    ("hold", "Enviado a espera"),
    ("handoff", "Entregado a otro rol"),
    ("stale", "Reclamo vencido"),
    ("takeover", "Tomado por otro operario"),
    ("supervisor", "Liberado por un responsable"),
    ("logout", "Sesión cerrada"),
]


class SngPickingClaim(models.Model):
    """Historial de reclamos: quién tuvo tomado cada documento y por cuánto tiempo.

    El bloqueo vigente vive en los campos ``sng_claim_*`` de la orden o el
    traslado. Este modelo guarda la pista de auditoría, que hasta ahora solo
    existía como texto libre dentro del chatter.
    """

    _name = "sng.picking.claim"
    _description = "Reclamo de alistado"
    _order = "claimed_at desc, id desc"

    source_model = fields.Selection(
        [("sale.order", "Orden de venta"), ("stock.picking", "Traslado")],
        string="Tipo de documento",
        required=True,
        index=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Orden de venta",
        ondelete="cascade",
        index=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Traslado",
        ondelete="cascade",
        index=True,
    )
    source_reference = fields.Char(string="Documento", index=True)
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Operario",
        required=True,
        index=True,
        ondelete="restrict",
    )
    partner_name = fields.Char(string="Nombre del operario")
    device_id = fields.Many2one(
        "sng.picking.device",
        string="Dispositivo",
        index=True,
        ondelete="set null",
    )
    role = fields.Selection(ROLES, string="Rol", required=True, index=True)

    stage_name = fields.Char(string="Etapa al reclamar")
    claimed_at = fields.Datetime(
        string="Tomado el",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    released_at = fields.Datetime(string="Liberado el", readonly=True)
    release_reason = fields.Selection(
        RELEASE_REASONS,
        string="Motivo de liberación",
        readonly=True,
    )
    released_by_id = fields.Many2one(
        "res.partner",
        string="Liberado por",
        readonly=True,
        ondelete="set null",
    )
    state = fields.Selection(
        [("held", "En curso"), ("released", "Liberado")],
        string="Estado",
        required=True,
        default="held",
        index=True,
    )
    duration_minutes = fields.Float(
        string="Minutos",
        compute="_compute_duration_minutes",
        help="Tiempo transcurrido desde que se tomó el documento.",
    )

    def _compute_duration_minutes(self):
        now = fields.Datetime.now()
        for record in self:
            if not record.claimed_at:
                record.duration_minutes = 0.0
                continue
            end = record.released_at or now
            record.duration_minutes = (end - record.claimed_at).total_seconds() / 60.0

    @api.depends("source_reference", "partner_name", "partner_id")
    def _compute_display_name(self):
        for record in self:
            label = "%s · %s" % (
                record.source_reference or _("Documento"),
                record.partner_name or record.partner_id.display_name or "",
            )
            record.display_name = label.strip(" ·")

    # ── Resolución y utilidades internas ─────────────────────────────────────

    @api.model
    def _resolve_source(self, source_model, source_id):
        if source_model not in SOURCE_MODELS:
            raise ValidationError(
                _("El tipo de documento '%s' no se puede reclamar.") % source_model
            )
        try:
            source_id = int(source_id)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                _("El identificador del documento no es válido.")
            ) from error
        record = self.env[source_model].browse(source_id)
        if not record.exists():
            raise ValidationError(_("No se encontró el documento solicitado."))
        return record

    @api.model
    def _resolve_partner(self, partner_id):
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                _("Se debe indicar qué operario está tomando el documento.")
            ) from error
        partner = self.env["res.partner"].browse(partner_id)
        if not partner.exists():
            raise ValidationError(_("El operario indicado no existe en Odoo."))
        return partner

    @api.model
    def _stage_field(self, record):
        return "sale_order_stages" if record._name == "sale.order" else "stage_id"

    @api.model
    def _lock_source(self, record):
        """Toma el bloqueo de la fila hasta que termine la transacción.

        Este es el corazón del módulo. Dos solicitudes simultáneas sobre el
        mismo documento se serializan aquí: la segunda espera, y cuando entra ya
        ve el reclamo que dejó la primera, así que la rechaza en vez de pisarla.
        """
        # El SELECT va por SQL directo, así que hay que bajar a base cualquier
        # escritura que el ORM tenga pendiente antes de pedir el bloqueo.
        self.env.flush_all()
        self.env.cr.execute(
            'SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % record._table,
            (record.id,),
        )
        # El ORM cachea los valores leídos antes del bloqueo; hay que descartarlos
        # para que la comprobación siguiente lea el estado real de la base.
        record.invalidate_recordset()

    @api.model
    def _timeout_minutes(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sng_picking_claim.timeout_minutes", "0")
        )
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @api.model
    def _is_stale(self, claimed_at):
        minutes = self._timeout_minutes()
        if not minutes or not claimed_at:
            return False
        return fields.Datetime.now() > claimed_at + timedelta(minutes=minutes)

    @api.model
    def _active_claim(self, record):
        domain = [("state", "=", "held")]
        if record._name == "sale.order":
            domain.append(("sale_order_id", "=", record.id))
        else:
            domain.append(("picking_id", "=", record.id))
        return self.sudo().search(domain, order="claimed_at desc", limit=1)

    @api.model
    def _close_active_claims(self, record, reason="done", released_by=None):
        domain = [("state", "=", "held")]
        if record._name == "sale.order":
            domain.append(("sale_order_id", "=", record.id))
        else:
            domain.append(("picking_id", "=", record.id))
        claims = self.sudo().search(domain)
        if claims:
            claims.write(
                {
                    "state": "released",
                    "released_at": fields.Datetime.now(),
                    "release_reason": reason,
                    "released_by_id": released_by.id if released_by else False,
                }
            )
        return claims

    @api.model
    def _open_claim(self, record, partner, device, role):
        stage = record[self._stage_field(record)]
        values = {
            "source_model": record._name,
            "source_reference": record.display_name,
            "company_id": record.company_id.id or self.env.company.id,
            "partner_id": partner.id,
            "partner_name": partner.display_name,
            "device_id": device.id if device else False,
            "role": role,
            "stage_name": stage.display_name if stage else False,
            "claimed_at": fields.Datetime.now(),
            "state": "held",
        }
        if record._name == "sale.order":
            values["sale_order_id"] = record.id
        else:
            values["picking_id"] = record.id
        return self.sudo().create(values)

    # ── Carga útil para la app ───────────────────────────────────────────────

    @api.model
    def _source_payload(self, record):
        stage = record[self._stage_field(record)]
        holder = record.sng_claim_partner_id
        device = record.sng_claim_device_id
        return {
            "source_model": record._name,
            "source_id": record.id,
            "reference": record.display_name,
            "stage_id": stage.id if stage else False,
            "stage_name": stage.display_name if stage else False,
            "claimed": bool(holder),
            "holder_partner_id": holder.id if holder else False,
            "holder_name": holder.display_name if holder else False,
            "holder_role": record.sng_claim_role or False,
            "device_id": device.id if device else False,
            "device_name": device.name if device else False,
            "claimed_at": (
                fields.Datetime.to_string(record.sng_claimed_at)
                if record.sng_claimed_at
                else False
            ),
            "stale": self._is_stale(record.sng_claimed_at),
        }

    # ── API móvil ────────────────────────────────────────────────────────────

    @api.model
    def mobile_claim(
        self,
        source_model,
        source_id,
        partner_id,
        role,
        target_stage_id=False,
        expected_stage_ids=False,
        device_uid=False,
        device_name=False,
        takeover=False,
    ):
        """Toma un documento en nombre de un operario y lo mueve de etapa.

        Devuelve la situación del documento si el reclamo prospera. Si ya lo
        tiene otra persona lanza ``UserError``, que la app no reintenta.
        """
        record = self._resolve_source(source_model, source_id)
        partner = self._resolve_partner(partner_id)
        if role not in dict(ROLES):
            raise ValidationError(_("El rol '%s' no es válido.") % role)

        device = self.env["sng.picking.device"]._touch(
            device_uid, device_name=device_name, partner=partner
        )

        self._lock_source(record)

        holder = record.sng_claim_partner_id
        is_refresh = bool(holder) and holder.id == partner.id

        if holder and not is_refresh:
            stale = self._is_stale(record.sng_claimed_at)
            if not takeover and not stale:
                previous_device = record.sng_claim_device_id
                raise UserError(
                    _(
                        "%(doc)s ya lo tomó %(user)s%(device)s.\n\n"
                        "Actualiza la lista para ver los documentos que siguen libres."
                    )
                    % {
                        "doc": record.display_name,
                        "user": holder.display_name,
                        "device": (
                            _(" desde %s") % previous_device.name
                            if previous_device
                            else ""
                        ),
                    }
                )
            self._close_active_claims(
                record,
                reason="stale" if stale and not takeover else "takeover",
                released_by=partner,
            )
            holder = self.env["res.partner"]

        stage_field = self._stage_field(record)
        current_stage = record[stage_field]

        if expected_stage_ids and not is_refresh:
            try:
                expected = {int(stage) for stage in expected_stage_ids}
            except (TypeError, ValueError) as error:
                raise ValidationError(
                    _("Las etapas esperadas no son válidas.")
                ) from error
            if current_stage and current_stage.id not in expected:
                raise UserError(
                    _(
                        "%(doc)s ya no está disponible: pasó a la etapa '%(stage)s'.\n\n"
                        "Actualiza la lista."
                    )
                    % {
                        "doc": record.display_name,
                        "stage": current_stage.display_name,
                    }
                )

        values = {
            "sng_claim_partner_id": partner.id,
            "sng_claim_role": role,
        }
        if device:
            values["sng_claim_device_id"] = device.id
        if not is_refresh:
            values["sng_claimed_at"] = fields.Datetime.now()
        if target_stage_id:
            values[stage_field] = int(target_stage_id)
        record.write(values)

        claim = self._active_claim(record)
        if claim and is_refresh:
            claim.write(
                {
                    "device_id": device.id if device else claim.device_id.id,
                    "role": role,
                    "source_reference": record.display_name,
                }
            )
        else:
            if claim:
                self._close_active_claims(record, reason="handoff", released_by=partner)
            claim = self._open_claim(record, partner, device, role)

        return self._source_payload(record)

    @api.model
    def mobile_release(
        self,
        source_model,
        source_id,
        partner_id=False,
        reason="done",
        target_stage_id=False,
        device_uid=False,
    ):
        """Suelta un documento y opcionalmente lo mueve a la etapa siguiente."""
        record = self._resolve_source(source_model, source_id)
        partner = self._resolve_partner(partner_id) if partner_id else None
        if reason not in dict(RELEASE_REASONS):
            reason = "done"

        if device_uid:
            self.env["sng.picking.device"]._touch(device_uid, partner=partner)

        self._lock_source(record)

        holder = record.sng_claim_partner_id
        if holder and partner and holder.id != partner.id and reason != "supervisor":
            raise UserError(
                _(
                    "No puedes liberar %(doc)s porque lo tiene %(user)s.\n\n"
                    "Pide a un responsable que lo libere desde Odoo."
                )
                % {"doc": record.display_name, "user": holder.display_name}
            )

        values = {
            "sng_claim_partner_id": False,
            "sng_claim_device_id": False,
            "sng_claimed_at": False,
            "sng_claim_role": False,
        }
        if target_stage_id:
            values[self._stage_field(record)] = int(target_stage_id)
        record.write(values)

        self._close_active_claims(record, reason=reason, released_by=partner)
        return self._source_payload(record)

    @api.model
    def mobile_get_status(self, sale_order_ids=None, picking_ids=None):
        """Situación de varios documentos, con la misma clave 'modelo:id' que usa la app."""
        result = {}
        sale_order_ids = [int(i) for i in (sale_order_ids or [])]
        picking_ids = [int(i) for i in (picking_ids or [])]

        if sale_order_ids:
            for order in self.env["sale.order"].browse(sale_order_ids).exists():
                result["sale.order:%s" % order.id] = self._source_payload(order)
        if picking_ids:
            for picking in self.env["stock.picking"].browse(picking_ids).exists():
                result["stock.picking:%s" % picking.id] = self._source_payload(picking)
        return result

    @api.model
    def mobile_get_mine(self, partner_id):
        """Documentos que el operario tiene tomados, en cualquier dispositivo.

        Permite que la app recupere el trabajo en curso aunque le hayan borrado
        los datos al equipo o el operario haya cambiado de tableta.
        """
        partner = self._resolve_partner(partner_id)
        payloads = []
        orders = self.env["sale.order"].search(
            [("sng_claim_partner_id", "=", partner.id)]
        )
        pickings = self.env["stock.picking"].search(
            [("sng_claim_partner_id", "=", partner.id)]
        )
        for record in list(orders) + list(pickings):
            payloads.append(self._source_payload(record))
        return payloads
