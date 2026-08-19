# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.tools import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        # Verificar stock antes de validar solo si hay usuarios configurados
        for picking in self:
            notification_users = picking.company_id.stock_notification_user_ids
            if not notification_users:
                continue

            # Solo aplicar a pickings donde la ubicación origen es interna
            # (entregas a clientes, transferencias internas, etc.)
            if picking.location_id.usage not in ("internal", "transit"):
                continue

            insufficient_moves = picking._sng_check_stock_availability()
            if insufficient_moves:
                picking._sng_send_stock_notification(insufficient_moves, notification_users)

        return super().button_validate()

    def _sng_check_stock_availability(self):
        """Retorna lista de diccionarios con movimientos que tienen stock insuficiente."""
        self.ensure_one()
        insufficient_moves = []
        precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")

        for move in self.move_ids.filtered(lambda m: m.state not in ("done", "cancel") and m.product_id.is_storable):
            # Cantidad que se intenta mover
            qty_to_move = move.quantity if not float_is_zero(move.quantity, precision_rounding=move.product_uom.rounding) else move.product_uom_qty

            if float_is_zero(qty_to_move, precision_rounding=move.product_uom.rounding):
                continue

            # Cantidad disponible en ubicación origen (considerando reservas existentes)
            available_qty = self.env["stock.quant"]._get_available_quantity(
                move.product_id,
                move.location_id,
                lot_id=False,
                package_id=False,
                owner_id=False,
                strict=False,
            )

            if float_compare(available_qty, qty_to_move, precision_digits=precision) < 0:
                insufficient_moves.append({
                    "move": move,
                    "product": move.product_id,
                    "location": move.location_id,
                    "required": qty_to_move,
                    "available": available_qty,
                    "shortage": qty_to_move - available_qty,
                })

        return insufficient_moves

    def _sng_send_stock_notification(self, insufficient_moves, notification_users):
        """Envía notificación por chat (discuss) y correo a los usuarios configurados."""
        self.ensure_one()
        partner_ids = notification_users.mapped("partner_id").ids
        if not partner_ids:
            return

        # Construir mensaje detallado
        body_lines = [
            _("⚠️ <b>Alerta de falta de stock</b>"),
            _("La entrega <b>%s</b> no puede validarse por falta de stock en la ubicación origen.", self._get_html_link()),
            "",
            _("<b>Productos con stock insuficiente:</b>"),
        ]

        for item in insufficient_moves:
            body_lines.append(_(
                "• <b>%(product)s</b> en <b>%(location)s</b><br/>"
                "&nbsp;&nbsp;Requerido: %(required).2f | Disponible: %(available).2f | Faltante: %(shortage).2f",
                product=item["product"].display_name,
                location=item["location"].display_name,
                required=item["required"],
                available=item["available"],
                shortage=item["shortage"],
            ))

        body = "<br/>".join(body_lines)

        # 1) Mensaje en el chatter del picking (notifica por Discuss a los partners mencionados)
        self.message_post(
            body=body,
            partner_ids=partner_ids,
            subtype_xmlid="mail.mt_comment",
        )

        # 2) Enviar correo electrónico usando la plantilla
        template = self.env.ref(
            "sng_stock_picking_notification.email_template_stock_shortage",
            raise_if_not_found=False,
        )
        if template:
            for user in notification_users:
                if user.email:
                    template.with_context(
                        insufficient_moves=insufficient_moves,
                        lang=user.lang or self.env.user.lang,
                    ).send_mail(
                        self.id,
                        force_send=True,
                        email_values={"email_to": user.email},
                        email_layout_xmlid="mail.mail_notification_layout",
                    )

        # 3) Crear actividad para cada usuario (aparece en su bandeja de actividades)
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if activity_type:
            for user in notification_users:
                self.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=user.id,
                    summary=_("Falta de stock en entrega %s", self.name),
                    note=body,
                )
