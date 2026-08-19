# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    auto_validate = fields.Boolean(
        string="Auto validar al crear",
        help="Si esta activo, los traslados de este tipo se validan automaticamente.",
    )
