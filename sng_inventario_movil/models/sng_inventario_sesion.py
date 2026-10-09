# -*- coding: utf-8 -*-
"""Sesión de inventario físico contada desde la app Android.

Flujo: borrador -> conteo (ronda 1, ciega) -> reconteo (ronda 2, solo las
diferencias que superan el umbral) -> revisión -> aplicado.

La app nunca recibe la cantidad del sistema. Cada lectura guarda en el
servidor la existencia del momento en que llegó (``qty_sistema``); al aplicar
se ajusta la *diferencia* contra esa foto y no contra la existencia actual,
así las ventas o entradas que ocurran mientras se cuenta no se pierden ni se
duplican en el ajuste.
"""
import logging
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero, plaintext2html

_logger = logging.getLogger(__name__)

GRUPO_CONTADOR = "sng_inventario_movil.group_contador"
GRUPO_RESPONSABLE = "sng_inventario_movil.group_responsable"
GRUPO_APROBADOR = "sng_inventory_adjustment_history.group_inventory_adjustment_approver"

ESTADOS_CONTEO = ("conteo", "reconteo")
ESTADOS_ABIERTOS = ("conteo", "reconteo", "revision")
COINCIDENCIAS = [
    ("barcode", "Código de barras"),
    ("referencia", "Referencia interna"),
    ("aproximada", "Referencia (dígito verificador distinto)"),
    ("manual", "Elegido a mano"),
]


class SngInventarioSesion(models.Model):
    _name = "sng.inventario.sesion"
    _description = "Sesión de inventario móvil"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    def _default_warehouse(self):
        return self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)

    name = fields.Char(
        string="Referencia", default=lambda self: _("Nuevo"), readonly=True,
        copy=False, tracking=True)
    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True, readonly=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    warehouse_id = fields.Many2one(
        "stock.warehouse", string="Almacén", required=True, check_company=True,
        default=_default_warehouse, tracking=True)
    location_id = fields.Many2one(
        "stock.location", string="Ubicación a contar", required=True,
        check_company=True, tracking=True,
        domain="[('usage', '=', 'internal'), ('warehouse_id', '=', warehouse_id)]",
        help="Se cuentan esta ubicación y todas sus sububicaciones internas.")
    tipo = fields.Selection(
        [("total", "Total: lo que no se cuente queda en cero"),
         ("parcial", "Parcial: solo se ajusta lo contado")],
        string="Tipo de inventario", default="total", required=True, tracking=True)
    umbral_unidades = fields.Float(
        string="Reconteo desde (unidades)", default=1.0, tracking=True,
        digits="Product Unit of Measure",
        help="Diferencia mínima, en unidades, para pedir un segundo conteo. "
             "Con 0 se reconteo toda diferencia.")
    umbral_valor = fields.Monetary(
        string="Reconteo desde (valor)", currency_field="currency_id", tracking=True,
        help="Diferencia mínima en valor (cantidad x costo) para pedir un segundo "
             "conteo aunque no alcance el umbral de unidades. Con 0 no se usa.")
    responsable_id = fields.Many2one(
        "res.users", string="Responsable", required=True, tracking=True,
        default=lambda self: self.env.user)
    contador_ids = fields.Many2many(
        "res.users", "sng_inv_sesion_contador_rel", "sesion_id", "user_id",
        string="Usuarios del conteo",
        domain=lambda self: [("groups_id", "in", self.env.ref(GRUPO_CONTADOR).id)],
        help="Usuarios de Odoo con que ingresan las tabletas. Vacío: cualquier "
             "usuario con el grupo Contador (app).")
    recontador_ids = fields.Many2many(
        "res.users", "sng_inv_sesion_recontador_rel", "sesion_id", "user_id",
        string="Usuarios del reconteo",
        domain=lambda self: [("groups_id", "in", self.env.ref(GRUPO_CONTADOR).id)],
        help="Vacío: los mismos del conteo.")
    dispositivo_ids = fields.Many2many(
        "sng.inventario.dispositivo", "sng_inv_sesion_dispositivo_rel", "sesion_id", "dispositivo_id",
        string="Tabletas del conteo", help="Vacío: cualquier tableta activa.")
    redispositivo_ids = fields.Many2many(
        "sng.inventario.dispositivo", "sng_inv_sesion_redispositivo_rel", "sesion_id", "dispositivo_id",
        string="Tabletas del reconteo", help="Vacío: las mismas del conteo.")
    reconteo_otra_tableta = fields.Boolean(
        "Reconteo con otra tableta", default=True, tracking=True,
        help="Una tableta no recuenta lo que ella misma contó en el conteo. Desactívelo "
             "si solo hay una tableta.")
    state = fields.Selection(
        [("borrador", "Borrador"),
         ("conteo", "Conteo"),
         ("reconteo", "Reconteo"),
         ("revision", "Revisión"),
         ("aplicado", "Aplicado"),
         ("cancelado", "Cancelado")],
        string="Estado", default="borrador", required=True, tracking=True,
        copy=False)
    ronda = fields.Integer(compute="_compute_ronda")
    fecha_inicio = fields.Datetime("Inicio del conteo", readonly=True, copy=False)
    fecha_cierre_conteo = fields.Datetime("Cierre del conteo", readonly=True, copy=False)
    fecha_cierre_reconteo = fields.Datetime("Cierre del reconteo", readonly=True, copy=False)
    fecha_aplicado = fields.Datetime("Fecha del ajuste", readonly=True, copy=False)
    aplicado_por_id = fields.Many2one("res.users", "Aplicado por", readonly=True, copy=False)
    nota = fields.Text("Observaciones")

    linea_ids = fields.One2many("sng.inventario.linea", "sesion_id", string="Líneas")
    lectura_ids = fields.One2many("sng.inventario.lectura", "sesion_id", string="Lecturas")
    move_ids = fields.One2many("stock.move", "sng_inventario_sesion_id", string="Movimientos")

    lectura_count = fields.Integer("Nº de lecturas", compute="_compute_indicadores")
    linea_count = fields.Integer("Productos", compute="_compute_indicadores")
    diferencia_count = fields.Integer("Con diferencia", compute="_compute_indicadores")
    reconteo_count = fields.Integer("A recontar", compute="_compute_indicadores")
    move_count = fields.Integer("Nº de movimientos", compute="_compute_indicadores")
    valor_faltante = fields.Monetary("Faltante", compute="_compute_indicadores")
    valor_sobrante = fields.Monetary("Sobrante", compute="_compute_indicadores")
    valor_neto = fields.Monetary("Diferencia neta", compute="_compute_indicadores")

    @api.depends("state")
    def _compute_ronda(self):
        for sesion in self:
            sesion.ronda = {"conteo": 1, "reconteo": 2}.get(sesion.state, 0)

    @api.depends("lectura_ids", "linea_ids.diferencia", "linea_ids.valor_diferencia",
                 "linea_ids.requiere_reconteo", "move_ids")
    def _compute_indicadores(self):
        for sesion in self:
            lineas = sesion.linea_ids
            con_diferencia = lineas.filtered(lambda l: not l._diferencia_es_cero())
            valores = con_diferencia.mapped("valor_diferencia")
            sesion.lectura_count = len(sesion.lectura_ids)
            sesion.linea_count = len(lineas)
            sesion.diferencia_count = len(con_diferencia)
            sesion.reconteo_count = len(lineas.filtered("requiere_reconteo"))
            sesion.move_count = len(sesion.move_ids)
            sesion.valor_faltante = sum(v for v in valores if v < 0)
            sesion.valor_sobrante = sum(v for v in valores if v > 0)
            sesion.valor_neto = sum(valores)

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        if self.warehouse_id and self.location_id.warehouse_id != self.warehouse_id:
            self.location_id = self.warehouse_id.lot_stock_id

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _ubicaciones(self):
        self.ensure_one()
        return self.env["stock.location"].sudo().search([
            ("id", "child_of", self.location_id.id), ("usage", "=", "internal"),
        ])

    def _usuarios_ronda(self, ronda=None):
        """Usuarios que pueden enviar lecturas en la ronda. Sin usuarios
        asignados vale cualquiera con el grupo Contador (app)."""
        self.ensure_one()
        ronda = ronda or self.ronda
        if ronda not in (1, 2):
            return self.env["res.users"]
        usuarios = (self.recontador_ids or self.contador_ids) if ronda == 2 else self.contador_ids
        return usuarios or self.env["res.users"].sudo().search(
            [("groups_id", "in", self.env.ref(GRUPO_CONTADOR).id)])

    def _dispositivo_permitido(self, dispositivo, ronda=None):
        self.ensure_one()
        ronda = ronda or self.ronda
        if ronda not in (1, 2):
            return False
        lista = (self.redispositivo_ids or self.dispositivo_ids) if ronda == 2 else self.dispositivo_ids
        return not lista or dispositivo in lista

    def _reconteo_para(self, dispositivo):
        """Líneas que esta tableta puede recontar."""
        self.ensure_one()
        lineas = self.linea_ids.filtered("requiere_reconteo")
        if self.reconteo_otra_tableta:
            lineas = lineas.filtered(lambda l: dispositivo not in l.dispositivo_ids)
        return lineas

    def _todos_los_contadores(self):
        self.ensure_one()
        return self.contador_ids | self.recontador_ids | self.lectura_ids.user_id

    def _check_responsable(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_RESPONSABLE):
            raise AccessError(_("Solo el responsable de inventario móvil puede hacer esta operación."))

    def _cantidades_sistema(self, product_ids=None, location_ids=None):
        """Existencia actual por (producto, ubicación) dentro del alcance."""
        self.ensure_one()
        dominio = [("location_id", "in", location_ids or self._ubicaciones().ids)]
        if product_ids is not None:
            dominio.append(("product_id", "in", list(product_ids)))
        grupos = self.env["stock.quant"].sudo()._read_group(
            dominio, ["product_id", "location_id"], ["quantity:sum"])
        return {(producto.id, ubicacion.id): cantidad
                for producto, ubicacion, cantidad in grupos}

    def _agregar_lecturas(self, ronda):
        """Suma las lecturas de una ronda por (producto, ubicación).

        La existencia de referencia es la que tenía el sistema cuando llegó la
        primera lectura de ese producto en esa ubicación."""
        self.ensure_one()
        datos = {}
        lecturas = self.lectura_ids.filtered(lambda l: l.ronda == ronda).sorted("id")
        for lectura in lecturas:
            clave = (lectura.product_id.id, lectura.location_id.id)
            dato = datos.setdefault(clave, {
                "qty": 0.0, "teorica": lectura.qty_sistema, "user_ids": set(),
                "por_dispositivo": {}, "ultimo_dispositivo": False,
            })
            dato["qty"] += lectura.qty
            dato["user_ids"].add(lectura.user_id.id)
            dispositivo = lectura.dispositivo_id
            dato["por_dispositivo"][dispositivo] = dato["por_dispositivo"].get(dispositivo, 0.0) + lectura.qty
            dato["ultimo_dispositivo"] = dispositivo
        return datos

    def _requiere_reconteo(self, diferencia, costo, rounding):
        self.ensure_one()
        if float_is_zero(diferencia, precision_rounding=rounding):
            return False
        if abs(diferencia) >= max(self.umbral_unidades, rounding):
            return True
        return bool(self.umbral_valor) and abs(diferencia * costo) >= self.umbral_valor

    def _notificar(self, usuarios, mensaje):
        self.ensure_one()
        partners = usuarios.partner_id
        self.message_post(
            body=mensaje, partner_ids=partners.ids,
            message_type="comment", subtype_xmlid="mail.mt_note")

    # ------------------------------------------------------------------
    # Acciones del responsable
    # ------------------------------------------------------------------
    def action_iniciar_conteo(self):
        self._check_responsable()
        for sesion in self:
            if sesion.state != "borrador":
                raise UserError(_("Solo se puede iniciar una sesión en borrador."))
            otras = self.search([
                ("id", "!=", sesion.id), ("state", "in", ESTADOS_ABIERTOS),
                ("company_id", "=", sesion.company_id.id),
            ])
            ruta = sesion.location_id.parent_path
            choques = otras.filtered(
                lambda o: o.location_id.parent_path.startswith(ruta)
                or ruta.startswith(o.location_id.parent_path))
            if choques:
                raise UserError(_(
                    "La sesión %(otra)s ya está contando %(ubicacion)s. "
                    "Ciérrela o cancélela antes de iniciar otra sobre las mismas ubicaciones.",
                    otra=choques[0].name, ubicacion=choques[0].location_id.complete_name))
            vals = {"state": "conteo", "fecha_inicio": fields.Datetime.now()}
            if sesion.name == _("Nuevo") or not sesion.name:
                vals["name"] = self.env["ir.sequence"].next_by_code("sng.inventario.sesion") or _("Nuevo")
            sesion.write(vals)
            sesion._notificar(sesion.responsable_id, _(
                "Conteo iniciado en %s. Ya pueden contar desde la app.",
                sesion.location_id.complete_name))
        return True

    def action_cerrar_conteo(self):
        self._check_responsable()
        Linea = self.env["sng.inventario.linea"].sudo().with_context(sng_inventario_sistema=True)
        for sesion in self:
            if sesion.state != "conteo":
                raise UserError(_("La sesión no está en conteo."))
            datos = sesion._agregar_lecturas(1)
            if not datos and sesion.tipo == "parcial":
                raise UserError(_("No hay lecturas para cerrar el conteo."))
            vals_list = []
            for (product_id, location_id), dato in datos.items():
                vals_list.append({
                    "sesion_id": sesion.id, "product_id": product_id,
                    "location_id": location_id, "contado1": True,
                    "conteo1": dato["qty"], "teorica1": dato["teorica"],
                    "contador_ids": [fields.Command.set(list(dato["user_ids"]))],
                    "dispositivo_ids": [fields.Command.set(
                        [d.id for d in dato["por_dispositivo"] if d])],
                })
            if sesion.tipo == "total":
                # Lo que el sistema tiene y nadie contó también es diferencia.
                for (product_id, location_id), cantidad in sesion._cantidades_sistema().items():
                    if (product_id, location_id) in datos or float_is_zero(cantidad, precision_digits=4):
                        continue
                    vals_list.append({
                        "sesion_id": sesion.id, "product_id": product_id,
                        "location_id": location_id, "contado1": False,
                        "conteo1": 0.0, "teorica1": cantidad,
                    })
            lineas = Linea.create(vals_list)
            for linea in lineas:
                producto = linea.product_id.with_company(sesion.company_id)
                costo = producto.standard_price
                linea.write({
                    "costo": costo,
                    "requiere_reconteo": sesion._requiere_reconteo(
                        linea.conteo1 - linea.teorica1, costo, linea.product_uom_id.rounding),
                })
            sesion.fecha_cierre_conteo = fields.Datetime.now()
            if any(lineas.mapped("requiere_reconteo")):
                sesion.state = "reconteo"
                sesion._notificar(sesion.responsable_id, _(
                    "Hay %s productos para recontar. Ábranlos en la app (ronda 2).",
                    len(lineas.filtered("requiere_reconteo"))))
            else:
                sesion._pasar_a_revision()
        return True

    def action_cerrar_reconteo(self):
        self._check_responsable()
        for sesion in self:
            if sesion.state != "reconteo":
                raise UserError(_("La sesión no está en reconteo."))
            datos = sesion._agregar_lecturas(2)
            for linea in sesion.linea_ids.filtered("requiere_reconteo"):
                dato = datos.get((linea.product_id.id, linea.location_id.id))
                if not dato:
                    continue
                # En el reconteo cada tableta cuenta el producto completo: no se
                # suman tabletas. Si dos lo recontaron y no coinciden, vale la
                # última y la línea queda marcada para revisión.
                totales = dato["por_dispositivo"]
                conteo2 = totales[dato["ultimo_dispositivo"]]
                distintos = len({round(q, 4) for q in totales.values()}) > 1
                vals = {
                    "contado2": True, "conteo2": conteo2, "teorica2": dato["teorica"],
                    "reconteo_conflicto": distintos,
                    "contador_ids": [fields.Command.link(uid) for uid in dato["user_ids"]],
                    "dispositivo_ids": [fields.Command.link(d.id) for d in totales if d],
                }
                if distintos:
                    vals["nota"] = _("Reconteos distintos: %s. Se tomó el último.", ", ".join(
                        "%s=%s" % (d.name or "?", q) for d, q in totales.items()))
                linea.sudo().with_context(sng_inventario_sistema=True).write(vals)
            sesion.fecha_cierre_reconteo = fields.Datetime.now()
            sesion._pasar_a_revision()
        return True

    def _pasar_a_revision(self):
        for sesion in self:
            for linea in sesion.linea_ids:
                if linea.contado2:
                    final, referencia = linea.conteo2, linea.teorica2
                elif linea.contado1:
                    final, referencia = linea.conteo1, linea.teorica1
                else:
                    final, referencia = 0.0, linea.teorica1
                linea.sudo().with_context(sng_inventario_sistema=True).write({
                    "qty_final": final, "teorica_ref": referencia,
                })
            sesion.state = "revision"
            sesion._notificar(sesion.responsable_id, _(
                "Conteo terminado: %s productos con diferencia. Revise y pida a "
                "Gerencia que aplique el ajuste.", sesion.diferencia_count))

    def action_aplicar_ajuste(self):
        self.ensure_one()
        if self.state != "revision":
            raise UserError(_("Solo se aplica una sesión en revisión."))
        if not self.env.user.has_group(GRUPO_APROBADOR):
            raise AccessError(_("Solo Gerencia autorizada puede aplicar ajustes de inventario."))
        if self.env.user in self._todos_los_contadores():
            raise AccessError(_(
                "Usted participó en el conteo de esta sesión. Otra persona de "
                "Gerencia debe aplicar el ajuste."))
        lineas = self.linea_ids.filtered(lambda l: not l._diferencia_es_cero())
        Quant = self.env["stock.quant"]
        existentes = Quant.sudo().search([
            ("product_id", "in", lineas.product_id.ids),
            ("location_id", "in", lineas.location_id.ids),
        ]).filtered(lambda q: (q.product_id, q.location_id) in {
            (l.product_id, l.location_id) for l in lineas})
        self._check_conflictos(existentes)

        contadores_sesion = self._todos_los_contadores()
        nuevas = {}
        for linea in lineas:
            actuales = Quant.sudo()._gather(linea.product_id, linea.location_id, strict=True)
            nuevas[linea] = (sum(actuales.mapped("quantity")), sum(actuales.mapped("reserved_quantity")))
        liberadas = self._liberar_reservas({
            linea: actual + linea.diferencia
            for linea, (actual, reservado) in nuevas.items()
            if linea.diferencia < 0 and actual + linea.diferencia < reservado
        })

        quants = Quant
        for linea in lineas:
            actual = nuevas[linea][0]
            nueva = actual + linea.diferencia
            # sudo: el registro de la cantidad contada la hicieron los contadores
            # desde la app; quien aplica no debe quedar como capturador.
            quant = Quant.sudo().with_context(inventory_mode=True).create({
                "product_id": linea.product_id.id,
                "location_id": linea.location_id.id,
                "inventory_quantity": nueva,
            })
            contadores = linea.contador_ids or contadores_sesion
            quant.sudo().write({
                "sng_counted_by_ids": [fields.Command.set(contadores.ids)],
                "sng_last_counted_by_id": contadores[:1].id,
                "sng_adjustment_reason": _("Inventario móvil %s", self.name),
            })
            linea.sudo().with_context(sng_inventario_sistema=True).write({
                "qty_sistema_aplicacion": actual,
            })
            quants |= quant
        if quants:
            quants.with_env(self.env).with_context(
                inventory_name=_("Inventario %s", self.name),
                sng_inventario_sesion_id=self.id,
            )._apply_inventory()
        if liberadas:
            # Se vuelve a reservar con la existencia que quedó.
            liberadas.sudo()._action_assign()
        self.write({
            "state": "aplicado", "fecha_aplicado": fields.Datetime.now(),
            "aplicado_por_id": self.env.uid,
        })
        cuerpo = _("Ajuste aplicado: %(n)s productos, diferencia neta %(valor)s.",
                   n=len(lineas), valor=self.currency_id.format(self.valor_neto))
        if liberadas:
            cuerpo += "\n" + _(
                "El conteo quedó por debajo de lo reservado; se liberaron y volvieron a "
                "reservar estas operaciones: %s",
                ", ".join(sorted(set(liberadas.mapped(lambda m: m.picking_id.name or m.reference or "")))))
        self.message_post(body=plaintext2html(cuerpo))
        return True

    def _liberar_reservas(self, minimos):
        """Odoo (con deltatech_stock_negative) no deja bajar la existencia por
        debajo de lo reservado para entregas pendientes. Para esos productos se
        anulan las reservas no preparadas; después del ajuste se vuelven a
        reservar con lo que haya. ``minimos``: {linea: existencia nueva}.
        Devuelve los movimientos liberados."""
        movimientos = self.env["stock.move"]
        problemas = []
        for linea, nueva in minimos.items():
            reservas = self.env["stock.move.line"].sudo().search([
                ("product_id", "=", linea.product_id.id),
                ("location_id", "=", linea.location_id.id),
                ("state", "not in", ("done", "cancel")),
                ("quantity", ">", 0),
            ])
            preparadas = sum(reservas.filtered("picked").mapped("quantity_product_uom"))
            if preparadas > nueva:
                problemas.append(_(
                    "%(p)s: hay %(r)s unidades ya preparadas en entregas y el conteo dejó %(n)s",
                    p=linea.product_id.display_name, r=preparadas, n=nueva))
                continue
            movimientos |= reservas.filtered(lambda ml: not ml.picked).move_id
        if problemas:
            raise UserError(_(
                "Antes de aplicar, revise estas entregas (tienen producto preparado que "
                "según el conteo no existe):\n%s", "\n".join(problemas)))
        if movimientos:
            movimientos.sudo()._do_unreserve()
        return movimientos

    def _check_conflictos(self, quants):
        """Las solicitudes de ajuste pendientes y los conteos cíclicos abiertos
        bloquean el ajuste nativo; se avisan todos juntos y con nombre."""
        pendientes = self.env["sng.inventory.adjustment.request"].sudo().search([
            ("quant_id", "in", quants.ids), ("state", "=", "pending"),
        ])
        problemas = [_("%s: solicitud de ajuste pendiente de aprobación", p.product_id.display_name)
                     for p in pendientes]
        if "sng_cycle_line_id" in quants._fields:
            problemas += [_("%s: está en un conteo cíclico abierto", q.product_id.display_name)
                          for q in quants.sudo().filtered("sng_cycle_line_id")]
        if problemas:
            raise UserError(_(
                "No se puede aplicar el ajuste mientras estos productos tengan "
                "otro proceso abierto:\n%s", "\n".join(problemas)))

    def action_cancelar(self):
        self._check_responsable()
        if any(s.state == "aplicado" for s in self):
            raise UserError(_("Una sesión aplicada no se puede cancelar."))
        self.write({"state": "cancelado"})
        return True

    def action_volver_borrador(self):
        self._check_responsable()
        for sesion in self:
            if sesion.state != "cancelado":
                raise UserError(_("Solo una sesión cancelada vuelve a borrador."))
            if sesion.lectura_ids:
                raise UserError(_("La sesión ya tiene lecturas; cree una sesión nueva."))
        self.write({"state": "borrador"})
        return True

    def action_guardar_codigos(self):
        """Guarda como código de barras del producto lo que el lector leyó,
        cuando el producto no tiene uno y el código no lo usa otro producto.
        Así la próxima lectura coincide exacto (sirve también a la app nativa)."""
        self._check_responsable()
        Product = self.env["product.product"].sudo().with_context(active_test=False)
        guardados, omitidos = [], []
        for sesion in self:
            codigos = {}
            for lectura in sesion.lectura_ids.filtered(
                    lambda l: l.codigo_leido and l.coincidencia != "barcode"):
                codigos.setdefault(lectura.product_id.sudo(), set()).add(lectura.codigo_leido.strip())
            for producto, leidos in codigos.items():
                if producto.barcode:
                    continue
                if len(leidos) > 1:
                    omitidos.append(_("%(p)s: se leyeron varios códigos (%(c)s)",
                                      p=producto.display_name, c=", ".join(sorted(leidos))))
                    continue
                codigo = leidos.pop()
                otro = Product.search([("barcode", "=", codigo), ("id", "!=", producto.id)], limit=1)
                if otro:
                    omitidos.append(_("%(p)s: el código %(c)s ya es de %(o)s",
                                      p=producto.display_name, c=codigo, o=otro.display_name))
                    continue
                producto.barcode = codigo
                guardados.append("%s → %s" % (producto.display_name, codigo))
            if guardados or omitidos:
                cuerpo = _("Códigos de barras guardados: %s", len(guardados))
                if omitidos:
                    cuerpo += "\n" + _("Omitidos:") + "\n" + "\n".join(omitidos)
                sesion.message_post(body=plaintext2html(cuerpo))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": _("Códigos de barras"),
                "message": _("Guardados: %(g)s. Omitidos: %(o)s (detalle en el historial).",
                             g=len(guardados), o=len(omitidos)),
                "type": "success" if guardados else "warning",
                "sticky": bool(omitidos),
            },
        }

    def action_ver_lecturas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Lecturas"),
            "res_model": "sng.inventario.lectura", "view_mode": "list",
            "domain": [("sesion_id", "=", self.id)],
            "context": {"search_default_group_dispositivo": 1},
        }

    def action_ver_movimientos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Movimientos del ajuste"),
            "res_model": "stock.move", "view_mode": "list,form",
            "domain": [("sng_inventario_sesion_id", "=", self.id)],
        }

    def unlink(self):
        if any(s.state not in ("borrador", "cancelado") for s in self):
            raise UserError(_("Solo se eliminan sesiones en borrador o canceladas."))
        if any(s.lectura_ids for s in self):
            raise UserError(_("La sesión tiene lecturas; cancélela en lugar de eliminarla."))
        return super().unlink()

    # ------------------------------------------------------------------
    # API de la app (JSON-RPC execute_kw). Las tabletas comparten usuario:
    # cada llamada trae el código de la tableta, que es lo que identifica
    # quién contó. Los métodos usan sudo después de validar usuario y
    # tableta; el contador no tiene acceso a las cantidades del sistema.
    # ------------------------------------------------------------------
    @api.model
    def _app_sesion(self, sesion_id, dispositivo):
        """(sesión, tableta) validadas para la ronda en curso."""
        tableta = self.env["sng.inventario.dispositivo"]._app_dispositivo(dispositivo)
        sesion = self.sudo().browse(int(sesion_id)).exists()
        if not sesion or sesion.company_id not in self.env.user.company_ids:
            raise AccessError(_("La sesión de inventario no existe."))
        if sesion.state in ESTADOS_CONTEO and (
                self.env.user not in sesion._usuarios_ronda()
                or not sesion._dispositivo_permitido(tableta)):
            raise AccessError(_("La tableta «%(t)s» no está asignada a la ronda actual de %(s)s.",
                                t=tableta.name, s=sesion.name))
        return sesion, tableta

    def _app_resumen(self, tableta=None):
        self.ensure_one()
        pendientes = 0
        if self.state == "reconteo":
            pendientes = len(self._reconteo_para(tableta) if tableta else self.linea_ids.filtered("requiere_reconteo"))
        return {
            "id": self.id,
            "nombre": self.name,
            "almacen": self.warehouse_id.name,
            "ubicacion": self.location_id.complete_name,
            "estado": self.state,
            "ronda": self.ronda,
            "tipo": self.tipo,
            "pendientes_reconteo": pendientes,
        }

    @api.model
    def app_sesiones(self, dispositivo):
        """Sesiones en las que esta tableta debe contar ahora."""
        tableta = self.env["sng.inventario.dispositivo"]._app_dispositivo(dispositivo)
        sesiones = self.sudo().search([
            ("state", "in", ESTADOS_CONTEO),
            ("company_id", "in", self.env.user.company_ids.ids),
        ])
        return [s._app_resumen(tableta) for s in sesiones
                if self.env.user in s._usuarios_ronda() and s._dispositivo_permitido(tableta)]

    @api.model
    def app_catalogo(self, sesion_id, dispositivo):
        """Ubicaciones y productos para resolver lecturas en la tableta.
        No incluye cantidades del sistema (conteo ciego)."""
        sesion, tableta = self._app_sesion(sesion_id, dispositivo)
        ubicaciones = [{
            "id": u.id, "nombre": u.complete_name, "barcode": u.barcode or "",
        } for u in sesion._ubicaciones()]
        productos = self.env["product.product"].sudo().search_read(
            [("is_storable", "=", True),
             ("company_id", "in", [False, sesion.company_id.id])],
            ["name", "default_code", "barcode", "uom_id"])
        reconteo = []
        if sesion.state == "reconteo":
            reconteo = [{"product_id": l.product_id.id, "location_id": l.location_id.id}
                        for l in sesion._reconteo_para(tableta)]
        return {
            "sesion": sesion._app_resumen(tableta),
            "ubicaciones": ubicaciones,
            "productos": [{
                "id": p["id"], "nombre": p["name"],
                "referencia": p["default_code"] or "", "barcode": p["barcode"] or "",
                "uom": p["uom_id"][1] if p["uom_id"] else "",
            } for p in productos],
            "reconteo": reconteo,
        }

    @api.model
    def app_mis_totales(self, sesion_id, dispositivo):
        """Lo que esta tableta lleva contado en la ronda actual (su propio
        conteo; no revela la existencia del sistema)."""
        sesion, tableta = self._app_sesion(sesion_id, dispositivo)
        grupos = self.env["sng.inventario.lectura"].sudo()._read_group(
            [("sesion_id", "=", sesion.id), ("ronda", "=", sesion.ronda),
             ("dispositivo_id", "=", tableta.id)],
            ["product_id", "location_id"], ["qty:sum"])
        return [{"product_id": p.id, "location_id": l.id, "qty": q} for p, l, q in grupos]

    @api.model
    def app_registrar(self, sesion_id, lecturas, dispositivo):
        """Registra un lote de lecturas. Idempotente por ``uuid``: si la app
        reintenta un envío, las lecturas ya guardadas se reportan aceptadas y
        no se duplican."""
        tableta = self.env["sng.inventario.dispositivo"]._app_dispositivo(dispositivo)
        sesion = self.sudo().browse(int(sesion_id)).exists()
        if not sesion or sesion.company_id not in self.env.user.company_ids:
            raise AccessError(_("La sesión de inventario no existe."))
        Lectura = self.env["sng.inventario.lectura"].sudo()
        uuids = [str(l.get("uuid") or "").strip() for l in lecturas]
        ya_guardadas = set(Lectura.search([("sng_uuid", "in", [u for u in uuids if u])]).mapped("sng_uuid"))
        ubicaciones = set(sesion._ubicaciones().ids)
        a_recontar = {(l.product_id.id, l.location_id.id)
                      for l in sesion.linea_ids.filtered("requiere_reconteo")}
        propios = a_recontar - {(l.product_id.id, l.location_id.id)
                                for l in sesion._reconteo_para(tableta)}
        product_ids = {int(l.get("product_id") or 0) for l in lecturas}
        productos = self.env["product.product"].sudo().with_context(active_test=False).browse(
            list(product_ids - {0})).exists()
        almacenables = set(productos.filtered("is_storable").ids)
        sistema = sesion._cantidades_sistema(product_ids=almacenables, location_ids=list(ubicaciones))

        aceptadas, rechazadas, nuevas = [], [], []
        for item, uuid in zip(lecturas, uuids):
            if not uuid:
                rechazadas.append({"uuid": "", "motivo": _("Lectura sin identificador.")})
                continue
            if uuid in ya_guardadas:
                aceptadas.append(uuid)
                continue
            motivo = sesion._app_validar_lectura(
                item, tableta, ubicaciones, a_recontar, propios, almacenables)
            if motivo:
                rechazadas.append({"uuid": uuid, "motivo": motivo})
                continue
            product_id, location_id = int(item["product_id"]), int(item["location_id"])
            coincidencia = item.get("coincidencia")
            nuevas.append({
                "sng_uuid": uuid,
                "sesion_id": sesion.id,
                "ronda": sesion.ronda,
                "user_id": self.env.uid,
                "dispositivo_id": tableta.id,
                "product_id": product_id,
                "location_id": location_id,
                "qty": float(item["qty"]),
                "qty_sistema": sistema.get((product_id, location_id), 0.0),
                "codigo_leido": (item.get("codigo") or "")[:64],
                "coincidencia": coincidencia if coincidencia in dict(COINCIDENCIAS) else False,
                "fecha_dispositivo": _parse_fecha(item.get("fecha")),
            })
            ya_guardadas.add(uuid)
            aceptadas.append(uuid)
        if nuevas:
            Lectura.create(nuevas)
        return {"aceptadas": aceptadas, "rechazadas": rechazadas, "sesion": sesion._app_resumen(tableta)}

    def _app_validar_lectura(self, item, tableta, ubicaciones, a_recontar, propios, almacenables):
        self.ensure_one()
        if self.state not in ESTADOS_CONTEO:
            return _("La sesión %s ya no está recibiendo conteos.", self.name)
        try:
            ronda = int(item.get("ronda") or 0)
            product_id = int(item.get("product_id") or 0)
            location_id = int(item.get("location_id") or 0)
            float(item.get("qty"))
        except (TypeError, ValueError):
            return _("Datos de la lectura inválidos.")
        if ronda != self.ronda:
            return _("La ronda %s ya se cerró; la lectura no se tomó en cuenta.", ronda)
        if self.env.user not in self._usuarios_ronda() or not self._dispositivo_permitido(tableta):
            return _("La tableta «%s» no está asignada a esta ronda de conteo.", tableta.name)
        if location_id not in ubicaciones:
            return _("La ubicación no pertenece a esta sesión.")
        if product_id not in almacenables:
            return _("El producto no existe o no lleva inventario.")
        if ronda == 2 and (product_id, location_id) not in a_recontar:
            return _("Ese producto no está en la lista de reconteo de esa ubicación.")
        if ronda == 2 and (product_id, location_id) in propios:
            return _("Esta tableta contó ese producto en el conteo; el reconteo lo hace otra tableta.")
        return False

    @api.model
    def app_terminar(self, sesion_id, dispositivo):
        """La tableta avisa al responsable que terminó su parte."""
        sesion, tableta = self._app_sesion(sesion_id, dispositivo)
        sesion._notificar(sesion.responsable_id, _(
            "La tableta «%(t)s» terminó su conteo (ronda %(r)s).", t=tableta.name, r=sesion.ronda))
        return True


def _parse_fecha(valor):
    """ISO 8601 de la app (con o sin zona) a datetime UTC sin zona."""
    if not valor:
        return False
    try:
        fecha = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return False
    if fecha.tzinfo:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    return fecha
