# -*- coding: utf-8 -*-

from odoo import _, fields, models


class SngPickingClaimMixin(models.AbstractModel):
    """Campos del reclamo vigente sobre un documento de bodega.

    Vive en la propia orden o traslado, y no en un modelo aparte, para que la
    lista de documentos disponibles se pueda filtrar en una sola consulta.
    """

    _name = "sng.picking.claim.mixin"
    _description = "Campos de reclamo de alistado"

    sng_claim_partner_id = fields.Many2one(
        "res.partner",
        string="Tomado por",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
        help="Operario que tiene el documento tomado desde la app de bodega.",
    )
    sng_claim_device_id = fields.Many2one(
        "sng.picking.device",
        string="Dispositivo",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    sng_claimed_at = fields.Datetime(
        string="Tomado el",
        copy=False,
        readonly=True,
    )
    sng_claim_role = fields.Selection(
        [
            ("bodega", "Bodega"),
            ("revision", "Revisión"),
            ("cedi", "CEDI / Relleno"),
        ],
        string="Rol que lo tomó",
        copy=False,
        readonly=True,
    )
    sng_is_claimed = fields.Boolean(
        string="Está tomado",
        compute="_compute_sng_is_claimed",
        search="_search_sng_is_claimed",
    )
    sng_claim_label = fields.Char(
        string="Reclamo",
        compute="_compute_sng_is_claimed",
    )

    def _compute_sng_is_claimed(self):
        for record in self:
            partner = record.sng_claim_partner_id
            record.sng_is_claimed = bool(partner)
            if not partner:
                record.sng_claim_label = False
                continue
            device = record.sng_claim_device_id
            record.sng_claim_label = (
                "%s · %s" % (partner.display_name, device.name)
                if device
                else partner.display_name
            )

    def _search_sng_is_claimed(self, operator, value):
        if operator not in ("=", "!="):
            raise NotImplementedError(
                _("Solo se admite buscar por igualdad sobre 'Está tomado'.")
            )
        claimed = bool(value) if operator == "=" else not value
        return [("sng_claim_partner_id", "!=" if claimed else "=", False)]

    def action_force_release_claim(self):
        """Libera el documento sin cambiarle la etapa.

        Es la salida para cuando la tableta se perdió, se dañó o el operario
        terminó su turno con el documento tomado.
        """
        claim_service = self.env["sng.picking.claim"]
        for record in self:
            claim_service.mobile_release(
                record._name,
                record.id,
                partner_id=self.env.user.partner_id.id,
                reason="supervisor",
            )
        return True

    def action_view_picking_claims(self):
        self.ensure_one()
        action = self.env.ref("sng_picking_claim.action_picking_claim").read()[0]
        field = "sale_order_id" if self._name == "sale.order" else "picking_id"
        action["domain"] = [(field, "=", self.id)]
        action["context"] = {"create": False}
        return action
