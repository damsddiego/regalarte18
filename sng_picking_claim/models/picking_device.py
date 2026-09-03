# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SngPickingDevice(models.Model):
    """Tableta o teléfono registrado que trabaja contra la app de bodega.

    El dispositivo genera su propio código la primera vez que arranca y lo manda
    en cada reclamo. El nombre legible se propone desde el dispositivo una sola
    vez, al registrarse; a partir de ahí manda el nombre que tenga en Odoo, para
    que un responsable pueda renombrar la tableta de forma centralizada.
    """

    _name = "sng.picking.device"
    _description = "Dispositivo de alistado"
    _order = "name"

    name = fields.Char(
        string="Nombre",
        required=True,
        index=True,
        help="Nombre legible del equipo, por ejemplo 'Tableta Bodega 3'.",
    )
    device_uid = fields.Char(
        string="Identificador",
        required=True,
        index=True,
        copy=False,
        readonly=True,
        help="Código generado por el propio dispositivo. No se edita a mano.",
    )
    active = fields.Boolean(string="Activo", default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    platform = fields.Char(string="Plataforma", readonly=True)
    app_version = fields.Char(string="Versión de la app", readonly=True)
    notes = fields.Text(string="Notas")

    first_seen_at = fields.Datetime(
        string="Registrado el",
        readonly=True,
        default=fields.Datetime.now,
    )
    last_seen_at = fields.Datetime(string="Última actividad", readonly=True)
    last_partner_id = fields.Many2one(
        "res.partner",
        string="Último operario",
        readonly=True,
    )

    claim_ids = fields.One2many(
        "sng.picking.claim",
        "device_id",
        string="Reclamos",
    )
    active_claim_count = fields.Integer(
        string="Documentos en curso",
        compute="_compute_active_claim_count",
    )

    _sql_constraints = [
        (
            "device_uid_uniq",
            "unique(device_uid)",
            "Ya existe un dispositivo registrado con ese identificador.",
        ),
    ]

    def _compute_active_claim_count(self):
        grouped = self.env["sng.picking.claim"]._read_group(
            [("device_id", "in", self.ids), ("state", "=", "held")],
            ["device_id"],
            ["__count"],
        )
        counts = {device.id: count for device, count in grouped}
        for record in self:
            record.active_claim_count = counts.get(record.id, 0)

    def action_view_claims(self):
        self.ensure_one()
        action = self.env.ref("sng_picking_claim.action_picking_claim").read()[0]
        action["domain"] = [("device_id", "=", self.id)]
        action["context"] = {"search_default_group_by_state": 1}
        return action

    # ── API móvil ────────────────────────────────────────────────────────────

    @api.model
    def _normalize_uid(self, device_uid):
        if not device_uid:
            return False
        value = str(device_uid).strip()
        if not value:
            return False
        if len(value) > 128:
            raise ValidationError(_("El identificador del dispositivo es demasiado largo."))
        return value

    @api.model
    def _touch(self, device_uid, device_name=False, platform=False, app_version=False, partner=None):
        """Devuelve el dispositivo registrado, creándolo si es la primera vez.

        Nunca pisa el nombre que ya tenga en Odoo: el nombre propuesto por el
        dispositivo solo se usa al crearlo.
        """
        uid = self._normalize_uid(device_uid)
        if not uid:
            return self.browse()

        device = self.sudo().with_context(active_test=False).search(
            [("device_uid", "=", uid)], limit=1
        )
        values = {"last_seen_at": fields.Datetime.now()}
        if platform:
            values["platform"] = str(platform)[:64]
        if app_version:
            values["app_version"] = str(app_version)[:32]
        if partner:
            values["last_partner_id"] = partner.id

        if device:
            device.write(values)
            return device

        proposed = (str(device_name).strip() if device_name else "") or _("Dispositivo %s") % uid[:8]
        values.update({"device_uid": uid, "name": proposed[:128]})
        return self.sudo().create(values)

    @api.model
    def mobile_register(self, device_uid, device_name=False, platform=False, app_version=False):
        """Registra el dispositivo y devuelve el nombre vigente en Odoo."""
        device = self._touch(
            device_uid,
            device_name=device_name,
            platform=platform,
            app_version=app_version,
        )
        if not device:
            raise ValidationError(_("El dispositivo debe enviar un identificador válido."))
        return device._mobile_payload()

    def _mobile_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "device_uid": self.device_uid or False,
            "name": self.name or False,
            "active": self.active,
            "platform": self.platform or False,
            "app_version": self.app_version or False,
            "first_seen_at": fields.Datetime.to_string(self.first_seen_at) if self.first_seen_at else False,
            "last_seen_at": fields.Datetime.to_string(self.last_seen_at) if self.last_seen_at else False,
        }
