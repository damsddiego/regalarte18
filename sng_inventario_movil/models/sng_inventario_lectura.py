# -*- coding: utf-8 -*-
from odoo import fields, models

from .sng_inventario_sesion import COINCIDENCIAS


class SngInventarioLectura(models.Model):
    """Cada envío de la app: una cantidad (positiva o negativa, para corregir)
    de un producto en una ubicación. Se suman al cerrar la ronda."""
    _name = "sng.inventario.lectura"
    _description = "Lectura de inventario móvil"
    _order = "id desc"

    sesion_id = fields.Many2one(
        "sng.inventario.sesion", string="Sesión", required=True,
        ondelete="cascade", index=True, readonly=True)
    company_id = fields.Many2one(related="sesion_id.company_id", store=True)
    ronda = fields.Integer("Ronda", required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, readonly=True, index=True)
    dispositivo_id = fields.Many2one(
        "sng.inventario.dispositivo", string="Tableta", readonly=True, index=True,
        context={"active_test": False})
    product_id = fields.Many2one("product.product", string="Producto", required=True, readonly=True)
    location_id = fields.Many2one("stock.location", string="Ubicación", required=True, readonly=True)
    qty = fields.Float("Cantidad", digits="Product Unit of Measure", readonly=True)
    qty_sistema = fields.Float(
        "Sistema al recibir", digits="Product Unit of Measure", readonly=True,
        help="Existencia del sistema cuando llegó la lectura (no se envía a la app).")
    codigo_leido = fields.Char("Código leído", readonly=True)
    coincidencia = fields.Selection(COINCIDENCIAS, string="Cómo se identificó", readonly=True)
    sng_uuid = fields.Char("UUID app", required=True, readonly=True, index=True, copy=False)
    fecha_dispositivo = fields.Datetime("Hora en el teléfono", readonly=True)

    _sql_constraints = [
        ("sng_uuid_unico", "unique(sng_uuid)", "La lectura ya fue registrada."),
    ]
