from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def mobile_dispatch_invoice_company_ids(self):
        if not self.env.user.has_group("sng_facturacion_despacho.group_facturar_despacho"):
            return []
        return [
            empresa.id for empresa in self.env.companies
            if self._facturacion_despacho_habilitada(empresa.id)
        ]

    @api.model
    def mobile_get_dispatch_invoice_status(self, order_id):
        if not self.env.user.has_group("sng_facturacion_despacho.group_facturar_despacho"):
            return self._resultado_facturacion_despacho("unavailable")
        orden = self._orden_facturacion_despacho(order_id)
        if not orden._facturacion_despacho_habilitada(orden.company_id.id):
            return orden._resultado_facturacion_despacho("unavailable")
        return orden._estado_facturacion_despacho()

    @api.model
    def mobile_invoice_dispatch(self, order_id, request_id):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            raise UserError(_("La solicitud de facturación no es válida."))
        orden = self._orden_facturacion_despacho(order_id)
        if not orden._facturacion_despacho_habilitada(orden.company_id.id):
            return orden._resultado_facturacion_despacho("unavailable")

        # La escritura serializa los RPC de una misma orden. En REPEATABLE READ
        # una transacción con una vista anterior se reintenta desde el servicio de Odoo.
        self.env.cr.execute(
            "UPDATE sale_order SET write_date = write_date WHERE id = %s",
            [orden.id],
        )
        estado = orden._estado_facturacion_despacho()
        if estado["status"] != "ready":
            return estado

        factura = orden.env["account.move"].browse(estado["invoice_id"] or [])
        if not factura:
            self.env["account.move"].check_access("create")
            try:
                with self.env.cr.savepoint():
                    factura = orden._create_invoices(final=True).with_env(orden.env)
                    if len(factura) != 1 or factura.move_type != "out_invoice":
                        raise UserError(_("Revise el documento de facturación en Odoo."))
                    if not orden._factura_coincide_con_entrega(factura, orden._lineas_facturables_despacho()):
                        raise UserError(_("Revise las cantidades de la factura en Odoo."))
            except UserError as error:
                return orden._resultado_facturacion_despacho("needs_review", mensaje=str(error))

        factura.check_access("write")
        operacion = orden._operacion_facturacion_despacho()
        if not operacion:
            operacion.create({
                "orden_id": orden.id,
                "factura_id": factura.id,
                "solicitud": request_id,
                "usuario_id": self.env.uid,
            })
            operacion = orden._operacion_facturacion_despacho()

        # Se conserva el borrador incluso si la localización rechaza la confirmación.
        try:
            with self.env.cr.savepoint():
                factura.with_context(sng_despacho_diferir_envio_hacienda=True).action_post()
        except UserError as error:
            return orden._resultado_facturacion_despacho("needs_review", factura, str(error))
        if factura.state != "posted":
            return orden._resultado_facturacion_despacho(
                "needs_review", factura,
                _("Odoo requiere revisar la confirmación de esta factura. Ábrala en Odoo."),
            )
        operacion.contabilizada = True
        return orden._resultado_facturacion_despacho("posted", factura)

    @api.model
    def _orden_facturacion_despacho(self, order_id):
        if not self.env.user.has_group("sng_facturacion_despacho.group_facturar_despacho"):
            raise AccessError(_("No tiene permiso para facturar desde Despacho."))
        if type(order_id) is not int or order_id <= 0:
            raise UserError(_("El pedido indicado no es válido."))
        orden = self.browse(order_id).exists()
        if not orden:
            raise AccessError(_("No tiene acceso al pedido."))
        orden.check_access("read")
        if orden.company_id not in self.env.companies:
            raise AccessError(_("No tiene acceso a la compañía del pedido."))
        # La llamada móvil no puede pasar opciones para saltarse validaciones fiscales.
        return orden.with_context(
            {}, allowed_company_ids=[orden.company_id.id], lang=self.env.user.lang,
        )

    @api.model
    def _facturacion_despacho_habilitada(self, company_id):
        return self.env["ir.config_parameter"].sudo().get_param(
            "sng_facturacion_despacho.habilitada.%s" % company_id
        ) == "1"

    def _operacion_facturacion_despacho(self):
        # Registro interno sin permisos directos por RPC.
        return self.env["sng.facturacion.despacho.operacion"].sudo().search([
            ("orden_id", "=", self.id),
        ], limit=1)

    def _estado_facturacion_despacho(self):
        resultado = self._resultado_facturacion_despacho
        if self.state != "sale":
            return resultado("needs_review", mensaje=_("El pedido no está confirmado."))

        salidas = self.picking_ids.filtered(
            lambda p: p.picking_type_id.code == "outgoing"
            and p.location_dest_id.usage == "customer" and not p.return_id
        )
        if not salidas.filtered(lambda p: p.state == "done"):
            return resultado(
                "pending_delivery", mensaje=_("Valide la salida al cliente en Odoo."),
            )
        lineas = self._lineas_facturables_despacho()
        if (self.order_line.filtered("is_downpayment") or not lineas
                or lineas.filtered(lambda l: l.product_id.invoice_policy != "delivery"
                                   or l.product_id.type == "combo")):
            return resultado(
                "needs_review", mensaje=_("Revise las líneas y la política de facturación del pedido en Odoo."),
            )
        if salidas.filtered(lambda p: p.state not in ("done", "cancel")):
            return resultado(
                "needs_review", mensaje=_("Revise la entrega parcial en Odoo."),
            )

        operacion = self._operacion_facturacion_despacho()
        facturas = self.invoice_ids.filtered(
            lambda f: f.move_type == "out_invoice" and f.state != "cancel"
            and f.invoice_line_ids.sale_line_ids.filtered(lambda l: not l.is_downpayment)
        )
        if operacion and operacion.factura_id.id not in facturas.ids:
            return resultado(
                "needs_review", mensaje=_("La factura de esta operación cambió. Revísela en Odoo."),
            )
        if facturas:
            if (len(facturas) != 1
                    or facturas.invoice_line_ids.sale_line_ids.order_id != self
                    or facturas.company_id != self.company_id
                    or facturas.partner_id != self.partner_invoice_id
                    or facturas.currency_id != self.currency_id
                    or any(
                        float_compare(
                            linea.qty_to_invoice, 0.0,
                            precision_rounding=linea.product_uom.rounding,
                        ) != 0 for linea in lineas
                    )):
                return resultado(
                    "needs_review", mensaje=_("Revise las facturas vinculadas al pedido en Odoo."),
                )
            if not self._factura_coincide_con_entrega(facturas, lineas):
                return resultado(
                    "needs_review", facturas,
                    _("La factura no coincide con las cantidades entregadas. Revísela en Odoo."),
                )
            if facturas.state == "posted":
                return resultado("posted", facturas)
            if operacion and operacion.contabilizada:
                return resultado(
                    "needs_review", facturas,
                    _("La factura volvió a borrador. Revísela en Odoo."),
                )
            return resultado("ready", facturas)

        if self.invoice_status == "to invoice":
            return resultado("ready")
        return resultado(
            "needs_review", mensaje=_("El pedido no tiene cantidades listas para facturar."),
        )

    def _lineas_facturables_despacho(self):
        return self.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)

    def _factura_coincide_con_entrega(self, factura, lineas):
        cantidades = dict.fromkeys(lineas.ids, 0.0)
        for renglon in factura.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            origen = renglon.sale_line_ids
            if factura.state == "posted" and not origen and (
                (renglon.name == "IVA Devuelto" and renglon.product_id.name == "IVA Devuelto")
                or (renglon.name == "Exoneración IVA" and not renglon.product_id)
            ):
                # La localización agrega estos ajustes fiscales al contabilizar.
                continue
            if (len(origen) != 1 or origen.id not in cantidades
                    or origen.product_id != renglon.product_id
                    or not renglon.product_uom_id
                    or renglon.product_uom_id.category_id != origen.product_uom.category_id):
                return False
            cantidades[origen.id] += renglon.product_uom_id._compute_quantity(
                renglon.quantity, origen.product_uom, round=False,
            )
        return all(
            float_compare(
                cantidades[linea.id], linea.qty_delivered,
                precision_rounding=linea.product_uom.rounding,
            ) == 0 for linea in lineas
        )

    @api.model
    def _resultado_facturacion_despacho(self, estado, factura=None, mensaje=None):
        return {
            "status": estado,
            "invoice_id": factura.id if factura else None,
            "invoice_name": (factura.name or None) if factura else None,
            "invoice_state": factura.state if factura else None,
            "electronic_state": (
                factura.state_tributacion or ("na" if factura.tipo_documento == "disabled" else None)
            ) if factura else None,
            "message": mensaje,
        }
