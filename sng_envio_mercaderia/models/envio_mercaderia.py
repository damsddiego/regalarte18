# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SngEnvioMercaderia(models.Model):
    _name = "sng.envio.mercaderia"
    _description = "Auditoría de envío de mercadería"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "document_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Documento",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Nuevo"),
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("confirmed", "Confirmado"),
            ("cancel", "Cancelado"),
        ],
        string="Estado",
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    document_date = fields.Datetime(
        string="Fecha del documento",
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )
    confirmed_at = fields.Datetime(string="Confirmado el", readonly=True, copy=False)
    confirmed_by_id = fields.Many2one(
        "res.users",
        string="Confirmado por",
        readonly=True,
        copy=False,
    )

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Orden de venta",
        ondelete="restrict",
        check_company=True,
        index=True,
        tracking=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Traslado",
        ondelete="restrict",
        check_company=True,
        index=True,
        tracking=True,
    )
    source_reference = fields.Char(
        string="Referencia de origen",
        readonly=True,
        copy=False,
        index=True,
    )
    mobile_request_key = fields.Char(
        string="Identificador de solicitud móvil",
        readonly=True,
        copy=False,
        index=True,
        help="Evita documentos duplicados cuando la aplicación reintenta una petición.",
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    delivery_partner_id = fields.Many2one(
        "res.partner",
        string="Contacto de entrega",
        ondelete="restrict",
        index=True,
        tracking=True,
    )

    company_name = fields.Char(string="Empresa", required=True)
    company_address = fields.Text(string="Dirección de la empresa")
    company_phone = fields.Char(string="Teléfono de la empresa")
    customer_name = fields.Char(string="Nombre del cliente", required=True)
    delivery_address = fields.Text(string="Lugar de entrega")
    contact_name = fields.Char(string="Contacto")
    contact_phone = fields.Char(string="Teléfono")

    customer_delivery_type_id = fields.Many2one(
        "res.partner.delivery.type",
        string="Método habitual al crear",
        ondelete="restrict",
        check_company=True,
        readonly=True,
        copy=False,
    )
    customer_delivery_method = fields.Char(
        string="Método habitual (histórico)",
        readonly=True,
        copy=False,
    )
    delivery_type_id = fields.Many2one(
        "res.partner.delivery.type",
        string="Método utilizado",
        ondelete="restrict",
        check_company=True,
        tracking=True,
    )
    delivery_method = fields.Char(
        string="Método utilizado (histórico)",
        readonly=True,
        copy=False,
    )
    delivery_method_status = fields.Selection(
        [
            ("missing", "Sin definir"),
            ("usual", "Método habitual"),
            ("assigned", "Asignado al cliente sin método"),
            ("changed", "Cambiado para este envío"),
        ],
        string="Comparación con el cliente",
        compute="_compute_delivery_method_audit",
        store=True,
        readonly=True,
    )
    delivery_method_changed = fields.Boolean(
        string="Método cambiado",
        compute="_compute_delivery_method_audit",
        store=True,
        readonly=True,
        index=True,
    )
    customer_method_updated = fields.Boolean(
        string="Ficha del cliente actualizada",
        readonly=True,
        copy=False,
        tracking=True,
    )
    customer_method_updated_at = fields.Datetime(
        string="Ficha actualizada el",
        readonly=True,
        copy=False,
    )
    customer_method_updated_by_id = fields.Many2one(
        "res.partner",
        string="Ficha actualizada por",
        readonly=True,
        copy=False,
    )

    box_number = fields.Integer(
        string="Caja número",
        required=True,
        default=1,
        tracking=True,
    )
    box_total = fields.Integer(
        string="Total de cajas",
        required=True,
        default=1,
        tracking=True,
    )
    boxes_label = fields.Char(
        string="Texto de cajas",
        compute="_compute_boxes_label",
        store=True,
        readonly=True,
    )

    picker_partner_id = fields.Many2one(
        "res.partner",
        string="Alistado por",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    picker_name = fields.Char(
        string="Alistado por (histórico)",
        readonly=True,
        copy=False,
    )
    picked_at = fields.Datetime(
        string="Alistado el",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    notes = fields.Text(string="Observaciones", tracking=True)

    print_count = fields.Integer(
        string="Impresiones registradas",
        default=0,
        readonly=True,
        copy=False,
    )
    last_printed_at = fields.Datetime(
        string="Última impresión",
        readonly=True,
        copy=False,
    )
    last_printed_by_id = fields.Many2one(
        "res.partner",
        string="Última impresión por",
        readonly=True,
        copy=False,
    )

    _sql_constraints = [
        (
            "mobile_request_key_unique",
            "unique(mobile_request_key)",
            "Ya existe una auditoría para esta solicitud móvil.",
        ),
    ]

    @api.depends("box_number", "box_total")
    def _compute_boxes_label(self):
        for record in self:
            if record.box_number > 0 and record.box_total > 0:
                record.boxes_label = "%s CAJA DE %s" % (
                    record.box_number,
                    record.box_total,
                )
            else:
                record.boxes_label = False

    @api.depends("customer_delivery_type_id", "delivery_type_id")
    def _compute_delivery_method_audit(self):
        for record in self:
            customer_method = record.customer_delivery_type_id
            used_method = record.delivery_type_id
            if not used_method:
                status = "missing"
            elif not customer_method:
                status = "assigned"
            elif customer_method == used_method:
                status = "usual"
            else:
                status = "changed"
            record.delivery_method_status = status
            record.delivery_method_changed = status == "changed"

    @api.constrains("box_number", "box_total")
    def _check_boxes(self):
        for record in self:
            if record.box_number < 1 or record.box_total < 1:
                raise ValidationError(_("Los valores de las cajas deben ser mayores que cero."))
            if record.box_number > record.box_total:
                raise ValidationError(_("La caja actual no puede ser mayor que el total de cajas."))

    @api.constrains("sale_order_id", "picking_id", "company_id")
    def _check_source_company(self):
        for record in self:
            if not record.sale_order_id and not record.picking_id:
                raise ValidationError(_("Debe indicar una orden de venta o un traslado."))
            if record.sale_order_id and record.sale_order_id.company_id != record.company_id:
                raise ValidationError(_("La orden pertenece a una compañía diferente."))
            if record.picking_id and record.picking_id.company_id != record.company_id:
                raise ValidationError(_("El traslado pertenece a una compañía diferente."))
            if (
                record.sale_order_id
                and record.picking_id
                and record.picking_id.sale_id
                and record.picking_id.sale_id != record.sale_order_id
            ):
                raise ValidationError(_("El traslado no pertenece a la orden seleccionada."))

    @api.onchange("sale_order_id", "picking_id")
    def _onchange_source(self):
        for record in self:
            source_values = record._prepare_source_values(
                sale_order=record.sale_order_id,
                picking=record.picking_id,
            )
            if source_values:
                for field_name, value in source_values.items():
                    if field_name in record._fields:
                        record[field_name] = value

    @api.onchange("delivery_type_id")
    def _onchange_delivery_type_id(self):
        for record in self:
            record.delivery_method = record.delivery_type_id.name or False

    @api.onchange("picker_partner_id")
    def _onchange_picker_partner_id(self):
        for record in self:
            record.picker_name = record.picker_partner_id.display_name or False

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for incoming_vals in vals_list:
            vals = dict(incoming_vals)
            if not vals.get("name") or vals.get("name") == _("Nuevo"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "sng.envio.mercaderia"
                ) or _("Nuevo")

            sale_order = self.env["sale.order"].browse(vals.get("sale_order_id")).exists()
            picking = self.env["stock.picking"].browse(vals.get("picking_id")).exists()
            source_values = self._prepare_source_values(
                sale_order=sale_order,
                picking=picking,
            )
            for field_name, value in source_values.items():
                vals.setdefault(field_name, value)

            delivery_type = self.env["res.partner.delivery.type"].browse(
                vals.get("delivery_type_id")
            ).exists()
            picker = self.env["res.partner"].browse(
                vals.get("picker_partner_id")
            ).exists()
            vals["delivery_method"] = delivery_type.name or False
            vals["picker_name"] = picker.display_name or False
            vals["source_reference"] = self._source_reference(sale_order, picking)
            prepared_vals_list.append(vals)

        return super().create(prepared_vals_list)

    def write(self, vals):
        protected_fields = {
            "company_id",
            "document_date",
            "sale_order_id",
            "picking_id",
            "partner_id",
            "delivery_partner_id",
            "company_name",
            "company_address",
            "company_phone",
            "customer_name",
            "delivery_address",
            "contact_name",
            "contact_phone",
            "customer_delivery_type_id",
            "customer_delivery_method",
            "delivery_type_id",
            "delivery_method",
            "box_number",
            "box_total",
            "picker_partner_id",
            "picker_name",
            "picked_at",
            "notes",
        }
        if (
            not self.env.context.get("allow_envio_audit_write")
            and protected_fields.intersection(vals)
            and any(record.state == "confirmed" for record in self)
        ):
            raise UserError(_("Una auditoría confirmada no puede modificarse."))

        vals = dict(vals)
        if "delivery_type_id" in vals:
            delivery_type = self.env["res.partner.delivery.type"].browse(
                vals.get("delivery_type_id")
            ).exists()
            vals["delivery_method"] = delivery_type.name or False
        if "picker_partner_id" in vals:
            picker = self.env["res.partner"].browse(
                vals.get("picker_partner_id")
            ).exists()
            vals["picker_name"] = picker.display_name or False
        return super().write(vals)

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Solo se pueden eliminar auditorías en borrador."))
        return super().unlink()

    def action_confirm(self):
        for record in self:
            if record.state != "draft":
                continue
            if not record.delivery_type_id:
                raise UserError(_("Debe seleccionar el método utilizado."))
            if not record.picker_partner_id:
                raise UserError(_("Debe indicar quién alistó la orden."))
            record.with_context(allow_envio_audit_write=True).write(
                {
                    "state": "confirmed",
                    "confirmed_at": fields.Datetime.now(),
                    "confirmed_by_id": self.env.user.id,
                    "delivery_method": record.delivery_type_id.name,
                    "picker_name": record.picker_partner_id.display_name,
                }
            )
            record.message_post(body=record._confirmation_message())
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "cancel":
                continue
            record.with_context(allow_envio_audit_write=True).write({"state": "cancel"})
            record.message_post(body=_("Auditoría cancelada."))
        return True

    def action_set_draft(self):
        if any(record.state != "cancel" for record in self):
            raise UserError(_("Solo una auditoría cancelada puede volver a borrador."))
        self.with_context(allow_envio_audit_write=True).write({"state": "draft"})
        return True

    def action_set_customer_default(self, actor_partner_id=False):
        for record in self:
            if record.state == "cancel":
                raise UserError(_("No se puede actualizar el cliente desde una auditoría cancelada."))
            if not record.delivery_type_id:
                raise UserError(_("Debe seleccionar el método utilizado."))

            target_partner = record.delivery_partner_id or record.partner_id
            if not target_partner:
                raise UserError(_("No se encontró el contacto que debe actualizarse."))

            actor = self.env["res.partner"].browse(actor_partner_id).exists()
            if not actor:
                actor = record.picker_partner_id

            previous_method = target_partner.delivery_type_id.name or _("Sin método")
            target_partner.write({"delivery_type_id": record.delivery_type_id.id})
            record.with_context(allow_envio_audit_write=True).write(
                {
                    "customer_method_updated": True,
                    "customer_method_updated_at": fields.Datetime.now(),
                    "customer_method_updated_by_id": actor.id,
                }
            )
            message = _(
                "Método habitual del contacto %(partner)s actualizado de "
                "%(previous)s a %(current)s por %(actor)s desde la auditoría %(audit)s."
            ) % {
                "partner": target_partner.display_name,
                "previous": previous_method,
                "current": record.delivery_type_id.name,
                "actor": actor.display_name,
                "audit": record.name,
            }
            record.message_post(body=message)
            if hasattr(target_partner, "message_post"):
                target_partner.message_post(body=message)
        return True

    def action_register_print(self, actor_partner_id=False):
        for record in self:
            if record.state != "confirmed":
                raise UserError(_("Solo se puede registrar la impresión de documentos confirmados."))
            actor = self.env["res.partner"].browse(actor_partner_id).exists()
            if not actor:
                actor = record.picker_partner_id
            record.with_context(allow_envio_audit_write=True).write(
                {
                    "print_count": record.print_count + 1,
                    "last_printed_at": fields.Datetime.now(),
                    "last_printed_by_id": actor.id,
                }
            )
            record.message_post(
                body=_("Impresión %(number)s registrada por %(actor)s.")
                % {"number": record.print_count, "actor": actor.display_name}
            )
        return True

    @api.model
    def mobile_get_defaults(self, source_model, source_id):
        sale_order, picking = self._resolve_mobile_source(source_model, source_id)
        values = self._prepare_source_values(sale_order=sale_order, picking=picking)
        customer_method_id = values.get("customer_delivery_type_id") or False
        suggested_method_id = customer_method_id

        if sale_order and sale_order.shipping_method:
            matching_method = self.env["res.partner.delivery.type"].search(
                [
                    ("name", "=ilike", sale_order.shipping_method.strip()),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", sale_order.company_id.id),
                ],
                limit=1,
            )
            if matching_method:
                suggested_method_id = matching_method.id

        return {
            "sale_order_id": sale_order.id or False,
            "sale_order_name": sale_order.name or False,
            "picking_id": picking.id or False,
            "picking_name": picking.name or False,
            "partner_id": values.get("partner_id") or False,
            "delivery_partner_id": values.get("delivery_partner_id") or False,
            "customer_name": values.get("customer_name") or False,
            "delivery_address": values.get("delivery_address") or False,
            "contact_name": values.get("contact_name") or False,
            "contact_phone": values.get("contact_phone") or False,
            "customer_delivery_type_id": customer_method_id,
            "customer_delivery_method": values.get("customer_delivery_method") or False,
            "suggested_delivery_type_id": suggested_method_id,
            "sale_shipping_method": sale_order.shipping_method if sale_order else False,
        }

    @api.model
    def mobile_create_or_get(
        self,
        source_model,
        source_id,
        box_number,
        box_total,
        delivery_type_id,
        picker_partner_id,
        request_key,
        confirm=False,
        notes=False,
    ):
        if not request_key or not str(request_key).strip():
            raise ValidationError(_("La solicitud móvil debe incluir un identificador único."))
        request_key = str(request_key).strip()

        try:
            box_number = int(box_number)
            box_total = int(box_total)
            delivery_type_id = int(delivery_type_id)
            picker_partner_id = int(picker_partner_id)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                _("Las cajas, el método de entrega y la persona que alistó deben ser válidos.")
            ) from error

        existing = self.search([("mobile_request_key", "=", request_key)], limit=1)
        if existing:
            return existing._mobile_payload()

        sale_order, picking = self._resolve_mobile_source(source_model, source_id)
        delivery_type = self.env["res.partner.delivery.type"].search(
            [("id", "=", delivery_type_id)],
            limit=1,
        )
        picker = self.env["res.partner"].search(
            [("id", "=", picker_partner_id)],
            limit=1,
        )
        if not delivery_type:
            raise ValidationError(_("El método de entrega seleccionado no existe."))
        if not picker:
            raise ValidationError(_("La persona que alistó la orden no existe."))

        source_values = self._prepare_source_values(sale_order=sale_order, picking=picking)
        audit = self.create(
            {
                **source_values,
                "sale_order_id": sale_order.id or False,
                "picking_id": picking.id or False,
                "box_number": box_number,
                "box_total": box_total,
                "delivery_type_id": delivery_type.id,
                "picker_partner_id": picker.id,
                "picked_at": fields.Datetime.now(),
                "mobile_request_key": request_key,
                "notes": notes or False,
            }
        )
        if confirm:
            audit.action_confirm()
        return audit._mobile_payload()

    @api.model
    def mobile_confirm(self, audit_id):
        audit = self.search([("id", "=", int(audit_id))], limit=1)
        if not audit:
            raise AccessError(_("No se encontró la auditoría solicitada."))
        audit.action_confirm()
        return audit._mobile_payload()

    @api.model
    def mobile_set_customer_default(self, audit_id, actor_partner_id=False):
        audit = self.search([("id", "=", int(audit_id))], limit=1)
        if not audit:
            raise AccessError(_("No se encontró la auditoría solicitada."))
        audit.action_set_customer_default(actor_partner_id=actor_partner_id)
        return audit._mobile_payload()

    @api.model
    def mobile_register_print(self, audit_id, actor_partner_id=False):
        audit = self.search([("id", "=", int(audit_id))], limit=1)
        if not audit:
            raise AccessError(_("No se encontró la auditoría solicitada."))
        audit.action_register_print(actor_partner_id=actor_partner_id)
        return audit._mobile_payload()

    def _mobile_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "sale_order_id": self.sale_order_id.id or False,
            "picking_id": self.picking_id.id or False,
            "box_number": self.box_number,
            "box_total": self.box_total,
            "boxes_label": self.boxes_label,
            "customer_delivery_type_id": self.customer_delivery_type_id.id or False,
            "customer_delivery_method": self.customer_delivery_method or False,
            "delivery_type_id": self.delivery_type_id.id or False,
            "delivery_method": self.delivery_method or False,
            "delivery_method_status": self.delivery_method_status,
            "delivery_method_changed": self.delivery_method_changed,
            "customer_method_updated": self.customer_method_updated,
            "picker_partner_id": self.picker_partner_id.id,
            "picker_name": self.picker_name,
            "print_count": self.print_count,
        }

    @api.model
    def _resolve_mobile_source(self, source_model, source_id):
        try:
            source_id = int(source_id)
        except (TypeError, ValueError) as error:
            raise ValidationError(_("El identificador de origen no es válido.")) from error

        if source_model == "sale.order":
            sale_order = self.env["sale.order"].search([("id", "=", source_id)], limit=1)
            if not sale_order:
                raise AccessError(_("No se encontró la orden de venta solicitada."))
            return sale_order, self.env["stock.picking"]

        if source_model == "stock.picking":
            picking = self.env["stock.picking"].search([("id", "=", source_id)], limit=1)
            if not picking:
                raise AccessError(_("No se encontró el traslado solicitado."))
            return picking.sale_id, picking

        raise ValidationError(_("El modelo de origen debe ser sale.order o stock.picking."))

    @api.model
    def _prepare_source_values(self, sale_order=False, picking=False):
        sale_order = sale_order.exists() if sale_order else self.env["sale.order"]
        picking = picking.exists() if picking else self.env["stock.picking"]
        if not sale_order and picking:
            sale_order = picking.sale_id
        if not sale_order and not picking:
            return {}

        company = sale_order.company_id if sale_order else picking.company_id
        partner = sale_order.partner_id if sale_order else picking.partner_id
        delivery_partner = (
            sale_order.partner_shipping_id
            if sale_order
            else (picking.partner_id or partner)
        )
        delivery_partner = delivery_partner or partner
        customer_method = (
            delivery_partner.delivery_type_id
            or partner.delivery_type_id
            if partner
            else self.env["res.partner.delivery.type"]
        )
        suggested_method = customer_method
        if sale_order and sale_order.shipping_method:
            matching_method = self.env["res.partner.delivery.type"].search(
                [
                    ("name", "=ilike", sale_order.shipping_method.strip()),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
            if matching_method:
                suggested_method = matching_method

        return {
            "company_id": company.id,
            "partner_id": partner.id,
            "delivery_partner_id": delivery_partner.id or False,
            "company_name": self._partner_display_name(company.partner_id) or company.name,
            "company_address": self._format_partner_address(company.partner_id),
            "company_phone": company.phone or company.partner_id.phone or company.partner_id.mobile,
            "customer_name": self._partner_display_name(partner),
            "delivery_address": self._format_partner_address(delivery_partner),
            "contact_name": delivery_partner.name or partner.name,
            "contact_phone": (
                delivery_partner.phone
                or delivery_partner.mobile
                or partner.phone
                or partner.mobile
            ),
            "customer_delivery_type_id": customer_method.id or False,
            "customer_delivery_method": customer_method.name or False,
            "delivery_type_id": suggested_method.id or False,
            "delivery_method": suggested_method.name or False,
        }

    @api.model
    def _partner_display_name(self, partner):
        if not partner:
            return False
        if "commercial_name" in partner._fields and partner.commercial_name:
            return partner.commercial_name
        return partner.name or partner.display_name

    @api.model
    def _format_partner_address(self, partner):
        if not partner:
            return False
        locality = ", ".join(
            part
            for part in [
                partner.city,
                partner.state_id.name,
                partner.country_id.name,
            ]
            if part
        )
        return ", ".join(
            part
            for part in [partner.street, partner.street2, locality]
            if part
        ) or False

    @api.model
    def _source_reference(self, sale_order=False, picking=False):
        references = []
        if sale_order:
            references.append(sale_order.name)
        if picking:
            references.append(picking.name)
        return " / ".join(references) or False

    def _confirmation_message(self):
        self.ensure_one()
        status_label = dict(self._fields["delivery_method_status"].selection).get(
            self.delivery_method_status,
            self.delivery_method_status,
        )
        return _(
            "Auditoría confirmada.<br/>"
            "Orden: %(order)s<br/>"
            "Cajas: %(boxes)s<br/>"
            "Método del cliente: %(customer_method)s<br/>"
            "Método utilizado: %(used_method)s<br/>"
            "Resultado: %(status)s<br/>"
            "Alistado por: %(picker)s"
        ) % {
            "order": self.source_reference or _("Sin referencia"),
            "boxes": self.boxes_label,
            "customer_method": self.customer_delivery_method or _("Sin método"),
            "used_method": self.delivery_method,
            "status": status_label,
            "picker": self.picker_name,
        }
