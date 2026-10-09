# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    sng_inventario_sesion_id = fields.Many2one(
        "sng.inventario.sesion", string="Inventario móvil", readonly=True,
        copy=False, index="btree_not_null")
