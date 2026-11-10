# -*- coding: utf-8 -*-

from odoo import models


class StockQuantityHistory(models.TransientModel):
    _inherit = "stock.quantity.history"

    def open_at_date(self):
        """"Inventario a la fecha" con el mismo panel de almacenes y grupos del reporte.

        La acción nativa abre una lista de productos sin ``js_class`` ni panel de
        búsqueda, así que no hay forma de escoger almacén ni grupo. Aquí se usa
        una lista con el ``js_class`` del reporte Existencias y su vista de
        búsqueda (que trae el panel de categorías, necesario para que el panel
        lateral se muestre). El contexto ``to_date`` se conserva.
        """
        action = super().open_at_date()
        tree_view_id = self.env.ref(
            "sng_warehouse_group_stock_reports.view_stock_product_tree_at_date"
        ).id
        form_view_id = self.env.ref("stock.product_form_view_procurement_button").id
        action["views"] = [(tree_view_id, "list"), (form_view_id, "form")]
        action["search_view_id"] = [
            self.env.ref("stock.product_search_form_view_stock_report").id,
            "search",
        ]
        return action
