from odoo import models, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        # Primero ejecuta la lógica estándar
        res = super().action_post()

        for move in self:
            if move.reference_code_id and move.reference_code_id.code == '06':
                # Solo Notas de Crédito de cliente ligadas a una factura
                if move.move_type != 'out_refund' or not move.reversed_entry_id:
                    continue

                original_invoice = move.reversed_entry_id
                pickings = original_invoice._get_related_pickings()
                if not pickings:
                    continue

                for picking in pickings.filtered(lambda p: p.state == 'done'):
                    return_moves = move._prepare_return_moves_for_picking(picking)
                    if not return_moves:
                        continue

                    return_picking = picking._create_return_picking_from_moves(return_moves)
                    if return_picking:
                        return_picking.button_validate()
                        move.message_post(
                            body=_(
                                "Se generó automáticamente la devolución de inventario "
                                "<b>%s</b> asociada a esta Nota de Crédito."
                            ) % return_picking.name
                        )

        return res

    # ---------- Helpers ---------- #

    def _get_related_pickings(self):
        """Obtiene los pickings (entregas) asociados a la factura original."""
        self.ensure_one()
        SaleOrder = self.env['sale.order']
        orders = SaleOrder.search([('name', '=', self.invoice_origin)])
        # Solo salidas de mercancía
        return orders.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')

    def _prepare_return_moves_for_picking(self, picking):
        """
        Calcula las cantidades a devolver para ESTE picking,
        basándose SOLO en las líneas de la Nota de Crédito (self).
        """
        self.ensure_one()
        return_moves = []  # lista de dicts {product_id, quantity}

        for line in self.invoice_line_ids:
            if not line.product_id or line.quantity <= 0:
                continue

            product = line.product_id

            # Movimientos de este picking para ese producto
            moves = picking.move_ids.filtered(lambda m: m.product_id == product)
            if not moves:
                continue

            # Cantidad enviada: suma de qty_done de TODAS las move_line_ids
            qty_sent = sum(moves.move_line_ids.mapped('qty_done'))

            # Cantidad ya devuelta: qty_done de los movimientos de retorno
            returned_moves = moves.mapped('returned_move_ids')
            qty_returned = sum(returned_moves.move_line_ids.mapped('qty_done'))

            qty_available = qty_sent - qty_returned
            if qty_available <= 0:
                continue

            # Solo devolvemos lo que pide la NC, sin superar lo disponible
            qty_to_return = min(line.quantity, qty_available)
            if qty_to_return <= 0:
                continue

            return_moves.append({
                'product_id': product,
                'quantity': qty_to_return,
            })

        return return_moves


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _create_return_picking_from_moves(self, return_moves):
        """
        Crea una devolución usando el wizard stock.return.picking,
        pero solo para los productos/cantidades indicados en return_moves.
        """
        self.ensure_one()
        if not return_moves:
            return False

        ReturnPicking = self.env['stock.return.picking']

        # Crear wizard
        wizard = ReturnPicking.create({
            'picking_id': self.id,
        })

        # Inicialmente Odoo llena product_return_moves con todos los productos;
        # aquí ajustamos cantidades solo para los productos de la NC.
        for wiz_line in wizard.product_return_moves:
            for rm in return_moves:
                if wiz_line.product_id == rm['product_id']:
                    wiz_line.quantity = rm['quantity']
                    break
            else:
                # Si el producto no está en la NC, no devolvemos nada.
                wiz_line.quantity = 0

        # Crear el picking de devolución
        res = wizard.action_create_returns()
        # En versiones recientes create_returns puede devolver un dict con acción,
        # por lo que obtenemos el picking de contexto o búsqueda
        if isinstance(res, dict):
            new_picking_id = res.get('res_id')
            return self.browse(new_picking_id)
        return False

