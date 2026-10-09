# -*- coding: utf-8 -*-
"""Avance en vivo de las sesiones en conteo (vista SQL, solo lectura).

Una fila por producto y ubicación: lo que ya se contó en la ronda 1 frente a
la existencia del sistema, y lo que tiene existencia y nadie ha contado. Solo
lo ven el responsable y Gerencia; las tabletas siguen contando a ciegas.

La existencia de comparación es la misma que usará el cierre: para lo
contado, la que había cuando llegó la primera lectura; para lo pendiente, la
actual."""
from odoo import _, fields, models, tools


class SngInventarioAvance(models.Model):
    _name = "sng.inventario.avance"
    _description = "Avance del conteo de inventario móvil"
    _auto = False
    _order = "estado desc, valor_diferencia, product_id"
    _rec_name = "product_id"
    # Para que Odoo guarde estos cambios pendientes antes de consultar la vista.
    _depends = {
        "sng.inventario.sesion": ["state", "tipo", "location_id", "company_id"],
        "sng.inventario.lectura": ["sesion_id", "ronda", "product_id", "location_id", "qty",
                                   "qty_sistema", "dispositivo_id"],
        "stock.quant": ["product_id", "location_id", "quantity"],
        "stock.location": ["parent_path", "usage"],
        "product.product": ["default_code", "standard_price", "product_tmpl_id"],
        "product.template": ["categ_id"],
    }

    sesion_id = fields.Many2one("sng.inventario.sesion", string="Sesión", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    default_code = fields.Char("Referencia", readonly=True)
    categ_id = fields.Many2one("product.category", string="Categoría", readonly=True)
    location_id = fields.Many2one("stock.location", string="Ubicación", readonly=True)
    estado = fields.Selection(
        [("pendiente", "Sin contar"), ("contado", "Contado")], string="Estado", readonly=True)
    contado = fields.Float("Contado", digits="Product Unit of Measure", readonly=True)
    sistema = fields.Float(
        "Sistema", digits="Product Unit of Measure", readonly=True,
        help="Existencia con la que se compara: la que había al llegar la primera lectura del "
             "producto o, si no se ha contado, la actual.")
    existencia_actual = fields.Float("Existencia actual", digits="Product Unit of Measure", readonly=True)
    diferencia = fields.Float(
        "Diferencia", digits="Product Unit of Measure", readonly=True,
        help="Contado menos sistema. En lo que falta por contar, es lo que se ajustaría si "
             "nadie lo cuenta (en inventario parcial no se ajusta: 0).")
    costo = fields.Float("Costo unitario", digits="Product Price", readonly=True)
    valor_diferencia = fields.Monetary("Valor diferencia", currency_field="currency_id", readonly=True)
    valor_sistema = fields.Monetary("Valor en sistema", currency_field="currency_id", readonly=True)
    lecturas = fields.Integer("Lecturas", readonly=True)
    tabletas = fields.Integer("Tabletas", readonly=True)
    dispositivo_id = fields.Many2one(
        "sng.inventario.dispositivo", string="Última tableta", readonly=True,
        context={"active_test": False})
    ultima_lectura = fields.Datetime("Última lectura", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # id = producto * 10^6 + ubicación: único porque dos sesiones abiertas
        # no pueden compartir ubicaciones, y estable entre lecturas de la vista.
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW sng_inventario_avance AS (
            WITH ses AS (
                SELECT s.id, s.company_id, s.tipo, l.parent_path
                  FROM sng_inventario_sesion s
                  JOIN stock_location l ON l.id = s.location_id
                 WHERE s.state = 'conteo'
            ), lec AS (
                SELECT r.sesion_id, r.product_id, r.location_id,
                       SUM(r.qty) AS qty,
                       (ARRAY_AGG(r.qty_sistema ORDER BY r.id))[1] AS sistema,
                       COUNT(*) AS lecturas,
                       COUNT(DISTINCT r.dispositivo_id) AS tabletas,
                       (ARRAY_AGG(r.dispositivo_id ORDER BY r.id DESC))[1] AS dispositivo_id,
                       MAX(r.create_date) AS ultima_lectura
                  FROM sng_inventario_lectura r
                  JOIN ses ON ses.id = r.sesion_id
                 WHERE r.ronda = 1
                 GROUP BY r.sesion_id, r.product_id, r.location_id
            ), sis AS (
                SELECT ses.id AS sesion_id, q.product_id, q.location_id, SUM(q.quantity) AS qty
                  FROM ses
                  JOIN stock_location l ON l.parent_path LIKE ses.parent_path || '%%'
                                       AND l.usage = 'internal'
                  JOIN stock_quant q ON q.location_id = l.id
                 GROUP BY ses.id, q.product_id, q.location_id
            ), filas AS (
                SELECT COALESCE(lec.sesion_id, sis.sesion_id) AS sesion_id,
                       COALESCE(lec.product_id, sis.product_id) AS product_id,
                       COALESCE(lec.location_id, sis.location_id) AS location_id,
                       lec.sesion_id IS NOT NULL AS contado_flag,
                       COALESCE(lec.qty, 0) AS contado,
                       COALESCE(lec.sistema, sis.qty, 0) AS sistema,
                       COALESCE(sis.qty, 0) AS existencia_actual,
                       COALESCE(lec.lecturas, 0) AS lecturas,
                       COALESCE(lec.tabletas, 0) AS tabletas,
                       lec.dispositivo_id,
                       lec.ultima_lectura
                  FROM lec
                  FULL OUTER JOIN sis
                    ON sis.sesion_id = lec.sesion_id
                   AND sis.product_id = lec.product_id
                   AND sis.location_id = lec.location_id
                 WHERE lec.sesion_id IS NOT NULL OR sis.qty <> 0
            )
            SELECT f.product_id::bigint * 1000000 + f.location_id AS id,
                   f.sesion_id,
                   ses.company_id,
                   f.product_id,
                   pp.default_code,
                   pt.categ_id,
                   f.location_id,
                   CASE WHEN f.contado_flag THEN 'contado' ELSE 'pendiente' END AS estado,
                   f.contado,
                   f.sistema,
                   f.existencia_actual,
                   CASE WHEN f.contado_flag THEN f.contado - f.sistema
                        WHEN ses.tipo = 'total' THEN -f.sistema
                        ELSE 0 END AS diferencia,
                   COALESCE((pp.standard_price ->> ses.company_id::text)::numeric, 0) AS costo,
                   (CASE WHEN f.contado_flag THEN f.contado - f.sistema
                         WHEN ses.tipo = 'total' THEN -f.sistema
                         ELSE 0 END)
                       * COALESCE((pp.standard_price ->> ses.company_id::text)::numeric, 0) AS valor_diferencia,
                   f.sistema * COALESCE((pp.standard_price ->> ses.company_id::text)::numeric, 0) AS valor_sistema,
                   f.lecturas,
                   f.tabletas,
                   f.dispositivo_id,
                   f.ultima_lectura
              FROM filas f
              JOIN ses ON ses.id = f.sesion_id
              JOIN product_product pp ON pp.id = f.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
            )
        """)

    def action_abrir_producto(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Lecturas de %s", self.product_id.display_name),
            "res_model": "sng.inventario.lectura", "view_mode": "list",
            "domain": [("sesion_id", "=", self.sesion_id.id), ("product_id", "=", self.product_id.id),
                       ("location_id", "=", self.location_id.id)],
        }
