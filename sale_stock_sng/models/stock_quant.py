# -*- coding: utf-8 -*-
from odoo import models, fields

class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Booleano “En mi bodega”, no almacenado, filtrable
    in_my_location = fields.Boolean(
        string='En mi bodega',
        compute='_compute_in_my_location',
        search='_search_in_my_location',
        store=False,
    )

    # ---- Internos ----
    def _get_user_root_location(self):
        """Devuelve la stock.location raíz según el partner del usuario.
           - Si partner.sale_location_id es stock.warehouse -> view_location_id
           - Si es stock.location -> esa misma
           - Si no hay nada -> False
        """
        partner = self.env.user.sudo().partner_id
        sale_loc = getattr(partner, 'sale_location_id', False)
        if not sale_loc:
            return False
        model = getattr(sale_loc, '_name', '')
        if model == 'stock.warehouse':
            return sale_loc.view_location_id
        if model == 'stock.location':
            return sale_loc
        return False

    def _compute_in_my_location(self):
        root = self._get_user_root_location()
        for q in self:
            if not root or not q.location_id:
                q.in_my_location = False
            else:
                # _is_child_of existe en 16/17/18; si no, sustituir por domain child_of
                q.in_my_location = q.location_id._is_child_of(root)

    def _search_in_my_location(self, operator, value):
        """Permite usar domain [('in_my_location','=',True)] sin tocar 'user' en el XML."""
        root = self._get_user_root_location()
        # Si no hay raíz configurada y piden True => no devolver nada
        if not root:
            return [('id', '=', 0)] if (operator in ('=', '==') and bool(value)) else []
        # Para '=' o '=='
        if operator in ('=', '=='):
            if bool(value):
                return [('location_id', 'child_of', root.id)]
            else:
                return ['!', ('location_id', 'child_of', root.id)]
        # Cualquier otro operador no aplica a booleanos; no filtrar adicional
        return []
