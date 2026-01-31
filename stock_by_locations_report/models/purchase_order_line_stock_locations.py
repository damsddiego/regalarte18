from odoo import fields, models, _


class PurchaseOrderLineStockLocations(models.Model):
    _inherit = 'purchase.order.line'

    def open_stock_locations(self):
        return {
            'name': 'Stock By Locations',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.locations.wizard',
            'view_mode': 'form',
            'target': 'new',  # Opens in a popup window
            # Pass the current purchase_order_line to the wizard
            'context': {'default_product_id': self.product_id.id},
        }
