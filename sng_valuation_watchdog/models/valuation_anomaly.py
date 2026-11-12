# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ValuationAnomaly(models.Model):
    """Una línea por producto y tipo de anomalía de valoración. La reconstruye
    sng.valuation.watchdog._refresh_anomalies (cron diario o botón Actualizar);
    los usuarios solo la leen."""

    _name = "sng.valuation.anomaly"
    _description = "Anomalía de valoración de inventario"
    _order = "anomaly_type, first_seen, id"
    _rec_name = "product_id"

    anomaly_type = fields.Selection(
        [
            ("descuadre", "Físico ≠ valorado"),
            ("entrada_precio_venta", "Entrada valorada a precio de venta"),
            ("margen", "Costo ≥ umbral del precio de venta"),
            ("costo_cero", "Stock con costo en 0"),
            ("svl_negativa", "Cantidad valorada negativa"),
        ],
        string="Problema",
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one("product.product", string="Producto", required=True, readonly=True, ondelete="cascade")
    default_code = fields.Char(related="product_id.default_code", string="Código")
    categ_id = fields.Many2one(related="product_id.categ_id", string="Categoría")
    move_id = fields.Many2one("stock.move", string="Movimiento", readonly=True, ondelete="cascade")
    reference = fields.Char(string="Referencia", readonly=True)
    qty_fisica = fields.Float(string="Físico", digits="Product Unit of Measure", readonly=True)
    qty_valorada = fields.Float(string="Valorado", digits="Product Unit of Measure", readonly=True)
    diferencia = fields.Float(string="Diferencia", digits="Product Unit of Measure", readonly=True)
    costo = fields.Float(string="Costo", digits="Product Price", readonly=True)
    precio_venta = fields.Float(string="Precio venta", digits="Product Price", readonly=True)
    margen_pct = fields.Float(string="Costo / precio (%)", digits=(16, 1), readonly=True)
    valor = fields.Float(string="Valor", digits="Product Price", readonly=True)
    first_seen = fields.Date(string="Detectado desde", readonly=True)
    dias = fields.Integer(string="Días", compute="_compute_dias")
    last_refresh = fields.Datetime(string="Última revisión", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, readonly=True)

    @api.depends("first_seen")
    def _compute_dias(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.dias = (today - rec.first_seen).days if rec.first_seen else 0

    def action_refresh(self):
        # Botón de encabezado de lista (display="always"): puede llegar con o sin selección.
        self.env["sng.valuation.watchdog"]._refresh_anomalies(self.env.company)
        return {"type": "ir.actions.client", "tag": "reload"}
