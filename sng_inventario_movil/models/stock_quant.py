# -*- coding: utf-8 -*-
from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _get_inventory_move_values(self, qty, location_id, location_dest_id,
                                   package_id=False, package_dest_id=False):
        values = super()._get_inventory_move_values(
            qty, location_id, location_dest_id,
            package_id=package_id, package_dest_id=package_dest_id)
        sesion_id = self.env.context.get("sng_inventario_sesion_id")
        if sesion_id:
            values["sng_inventario_sesion_id"] = sesion_id
        return values
