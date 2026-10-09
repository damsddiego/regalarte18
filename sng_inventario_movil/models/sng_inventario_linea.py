# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

# Lo único que el responsable corrige a mano en revisión; el resto lo
# calcula el servidor a partir de las lecturas.
CAMPOS_EDITABLES = {"qty_final", "nota"}


class SngInventarioLinea(models.Model):
    _name = "sng.inventario.linea"
    _description = "Línea de inventario móvil"
    _order = "sesion_id, location_id, product_id"

    sesion_id = fields.Many2one(
        "sng.inventario.sesion", string="Sesión", required=True,
        ondelete="cascade", index=True)
    company_id = fields.Many2one(related="sesion_id.company_id", store=True)
    currency_id = fields.Many2one(related="sesion_id.currency_id")
    state = fields.Selection(related="sesion_id.state", string="Estado")
    product_id = fields.Many2one("product.product", string="Producto", required=True, index=True)
    default_code = fields.Char(related="product_id.default_code", string="Referencia")
    product_uom_id = fields.Many2one(related="product_id.uom_id", string="Unidad")
    location_id = fields.Many2one("stock.location", string="Ubicación", required=True)

    teorica1 = fields.Float("Sistema (conteo)", digits="Product Unit of Measure", readonly=True)
    conteo1 = fields.Float("Conteo", digits="Product Unit of Measure", readonly=True)
    contado1 = fields.Boolean("Contado", readonly=True)
    requiere_reconteo = fields.Boolean("Pide reconteo", readonly=True)
    teorica2 = fields.Float("Sistema (reconteo)", digits="Product Unit of Measure", readonly=True)
    conteo2 = fields.Float("Reconteo", digits="Product Unit of Measure", readonly=True)
    contado2 = fields.Boolean("Recontado", readonly=True)

    qty_final = fields.Float(
        "Cantidad final", digits="Product Unit of Measure",
        help="Cantidad física que se aplicará. Sale del reconteo si lo hubo, "
             "si no del conteo; en inventario total, lo no contado queda en 0.")
    teorica_ref = fields.Float(
        "Sistema de referencia", digits="Product Unit of Measure", readonly=True,
        help="Existencia del sistema cuando se contó el producto. La diferencia "
             "se calcula contra esta cantidad, no contra la existencia al aplicar.")
    diferencia = fields.Float(
        "Diferencia", digits="Product Unit of Measure",
        compute="_compute_diferencia", store=True)
    costo = fields.Float("Costo unitario", digits="Product Price", readonly=True)
    valor_diferencia = fields.Monetary(
        "Valor diferencia", currency_field="currency_id",
        compute="_compute_diferencia", store=True)
    ajuste_manual = fields.Boolean("Corregido a mano", readonly=True)
    nota = fields.Char("Nota")
    contador_ids = fields.Many2many(
        "res.users", "sng_inv_linea_contador_rel", "linea_id", "user_id",
        string="Contado por", readonly=True)
    dispositivo_ids = fields.Many2many(
        "sng.inventario.dispositivo", "sng_inv_linea_dispositivo_rel", "linea_id", "dispositivo_id",
        string="Tabletas", readonly=True, context={"active_test": False})
    reconteo_conflicto = fields.Boolean(
        "Reconteos distintos", readonly=True,
        help="Dos o más tabletas recontaron el producto con cantidades distintas; se tomó la última.")
    qty_sistema_aplicacion = fields.Float(
        "Sistema al aplicar", digits="Product Unit of Measure", readonly=True)

    _sql_constraints = [
        ("producto_ubicacion_unico", "unique(sesion_id, product_id, location_id)",
         "El producto ya tiene una línea en esa ubicación para esta sesión."),
    ]

    @api.depends("qty_final", "teorica_ref", "costo")
    def _compute_diferencia(self):
        for linea in self:
            linea.diferencia = linea.qty_final - linea.teorica_ref
            linea.valor_diferencia = linea.diferencia * linea.costo

    def _diferencia_es_cero(self):
        self.ensure_one()
        return float_is_zero(self.diferencia, precision_rounding=self.product_uom_id.rounding or 0.01)

    def write(self, vals):
        if not self.env.context.get("sng_inventario_sistema"):
            if set(vals) - CAMPOS_EDITABLES:
                raise AccessError(_("Las cantidades del conteo las calcula el servidor."))
            if "qty_final" in vals:
                if any(linea.state != "revision" for linea in self):
                    raise UserError(_("La cantidad final solo se corrige en revisión."))
                vals = dict(vals, ajuste_manual=True)
                return super(SngInventarioLinea, self.with_context(sng_inventario_sistema=True)).write(vals)
        return super().write(vals)
