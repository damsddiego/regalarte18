# -*- coding: utf-8 -*-
from odoo import fields, models


class SngComparativoLine(models.Model):
    _name = "sng.comparativo.line"
    _description = "Línea de Comparativo de Ventas"
    _order = "descripcion asc"

    product_id = fields.Many2one("product.product", string="Producto", ondelete="cascade")
    company_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
        readonly=True,
    )
    codigo = fields.Char(string="Código")
    descripcion = fields.Char(string="Descripción")
    costo = fields.Monetary(
        string="Costo",
        currency_field="company_currency_id",
        groups="custom_ui_security.group_view_product_cost",
    )
    precio = fields.Monetary(
        string="Precio",
        currency_field="company_currency_id",
    )
    mes_6 = fields.Float(string="Hace 6 meses", digits=(12, 0))
    mes_5 = fields.Float(string="Hace 5 meses", digits=(12, 0))
    mes_4 = fields.Float(string="Hace 4 meses", digits=(12, 0))
    mes_3 = fields.Float(string="Hace 3 meses", digits=(12, 0))
    mes_2 = fields.Float(string="Hace 2 meses", digits=(12, 0))
    mes_1 = fields.Float(string="Hace 1 mes", digits=(12, 0))
    total_6m = fields.Float(string="Total 6 meses", digits=(12, 0))
    promedio_mensual = fields.Float(string="Prom. Mensual", digits=(12, 1))
    inv_actual = fields.Float(string="Inv. Actual", digits=(12, 0))
    meses_inventario = fields.Float(string="Meses Inv.", digits=(12, 1))
    proveedor = fields.Char(string="Proveedor")
