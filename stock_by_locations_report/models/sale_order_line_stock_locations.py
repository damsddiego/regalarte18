from odoo import fields, models, _


class SaleOrderLineStockLocations(models.Model):
    _inherit = 'sale.order.line'

    def open_stock_locations(self):
        return {
            'name': 'Stock By Locations',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.locations.wizard',
            'view_mode': 'form',
            'target': 'new',  # Opens in a popup window
            # Pass the current sale_order_line to the wizard
            'context': {'default_product_id': self.product_id.id,
                        'default_warehouse': self.order_id.warehouse_id.lot_stock_id.id,
                        },
        }
