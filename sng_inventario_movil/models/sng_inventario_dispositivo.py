# -*- coding: utf-8 -*-
"""Tabletas que cuentan inventario.

Las tabletas comparten un mismo usuario de Odoo, así que lo que identifica
quién contó es la tableta: cada instalación de la app genera un código único
y se registra con un nombre ("Tableta 1"). Desactivar el registro bloquea esa
tableta. El código identifica, no autentica: la seguridad sigue siendo el
usuario y la clave de Odoo."""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .sng_inventario_sesion import GRUPO_CONTADOR


class SngInventarioDispositivo(models.Model):
    _name = "sng.inventario.dispositivo"
    _description = "Tableta de inventario móvil"
    _order = "name"

    name = fields.Char("Nombre", required=True)
    codigo = fields.Char("Código de la instalación", required=True, readonly=True, copy=False, index=True)
    active = fields.Boolean("Activa", default=True,
                            help="Una tableta archivada no puede enviar lecturas.")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    fecha_registro = fields.Datetime("Registrada", readonly=True, default=fields.Datetime.now)
    ultima_conexion = fields.Datetime("Última conexión", readonly=True)
    version_app = fields.Char("Versión de la app", readonly=True)
    usuario_id = fields.Many2one("res.users", "Último usuario", readonly=True)
    nota = fields.Char("Nota", help="Por ejemplo, marca y número de serie.")
    lectura_count = fields.Integer("Lecturas", compute="_compute_lectura_count")

    _sql_constraints = [
        ("codigo_unico", "unique(codigo)", "Esa instalación de la app ya está registrada."),
    ]

    def _compute_lectura_count(self):
        datos = dict(self.env["sng.inventario.lectura"]._read_group(
            [("dispositivo_id", "in", self.ids)], ["dispositivo_id"], ["__count"]))
        for dispositivo in self:
            dispositivo.lectura_count = datos.get(dispositivo, 0)

    @api.constrains("name", "active", "company_id")
    def _check_nombre_unico(self):
        for dispositivo in self.filtered("active"):
            if self.search_count([
                ("id", "!=", dispositivo.id), ("company_id", "=", dispositivo.company_id.id),
                ("name", "=ilike", dispositivo.name.strip()),
            ]):
                raise UserError(_("Ya hay otra tableta activa llamada «%s». Use otro nombre.",
                                  dispositivo.name))

    def action_ver_lecturas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Lecturas de %s", self.name),
            "res_model": "sng.inventario.lectura", "view_mode": "list",
            "domain": [("dispositivo_id", "=", self.id)],
            "context": {"search_default_group_sesion": 1},
        }

    # ------------------------------------------------------------------
    # API de la app
    # ------------------------------------------------------------------
    @api.model
    def _app_dispositivo(self, codigo):
        """Tableta registrada y activa con ese código (sudo)."""
        if not self.env.user.has_group(GRUPO_CONTADOR):
            raise AccessError(_("Su usuario no es contador de inventario móvil."))
        codigo = str(codigo or "").strip()
        dispositivo = self.sudo().with_context(active_test=False).search([("codigo", "=", codigo)], limit=1)
        if not codigo or not dispositivo:
            raise AccessError(_("Esta tableta no está registrada. Cierre sesión y vuelva a ingresar."))
        if not dispositivo.active:
            raise AccessError(_("La tableta «%s» está desactivada en Odoo.", dispositivo.name))
        ahora = fields.Datetime.now()
        if not dispositivo.ultima_conexion or ahora - dispositivo.ultima_conexion > timedelta(minutes=5):
            dispositivo.write({"ultima_conexion": ahora, "usuario_id": self.env.uid})
        return dispositivo

    @api.model
    def app_registrar_dispositivo(self, codigo, nombre=None, version=None):
        """Registra la tableta la primera vez y la renombra si se envía un
        nombre. Devuelve el nombre vigente (el de Odoo manda si se cambió ahí)."""
        if not self.env.user.has_group(GRUPO_CONTADOR):
            raise AccessError(_("Su usuario no es contador de inventario móvil."))
        codigo = str(codigo or "").strip()
        nombre = str(nombre or "").strip()
        if len(codigo) < 8:
            raise UserError(_("Código de tableta inválido."))
        Dispositivo = self.sudo().with_context(active_test=False)
        dispositivo = Dispositivo.search([("codigo", "=", codigo)], limit=1)
        vals = {"ultima_conexion": fields.Datetime.now(), "usuario_id": self.env.uid}
        if version:
            vals["version_app"] = str(version)[:32]
        if not dispositivo:
            if not nombre:
                raise UserError(_("Indique el nombre de esta tableta."))
            dispositivo = Dispositivo.create(dict(vals, codigo=codigo, name=nombre,
                                                  company_id=self.env.company.id))
        else:
            if not dispositivo.active:
                raise AccessError(_("La tableta «%s» está desactivada en Odoo.", dispositivo.name))
            if nombre and nombre != dispositivo.name:
                vals["name"] = nombre
            dispositivo.write(vals)
        return {"id": dispositivo.id, "nombre": dispositivo.name}
