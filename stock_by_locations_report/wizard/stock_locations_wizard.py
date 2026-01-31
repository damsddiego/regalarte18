from odoo import models, fields, api


class StockLocationsWizard(models.TransientModel):
    _name = 'stock.locations.wizard'
    _description = 'Stock Locations Wizard'

    product_location_ids = fields.One2many('product.analysis.report', 'product_id', string='Product Locations', readonly=True)
    
    product_id = fields.Many2one('product.product', string='product', readonly=True)
    def_warehouse = fields.Many2one('stock.location', string="Default Warehouse", readonly=True)
    qty_def_warehouse = fields.Float(string="Qty On Hand In Default Warehouse", compute='_compute_qty_def_warehouse', readonly=True)
    total_qty_on_hand = fields.Float(string="Total On Hand", compute='_compute_total_qty_on_hand', readonly=True)

    @api.model
    def default_get(self, fields):
        res = super(StockLocationsWizard, self).default_get(fields)
        # Get the product_id from the context
        product_id = self._context.get('default_product_id')
        if product_id:
            # Fetch the product record for the given product_id
            product = self.env['product.product'].browse(product_id)
            if product.exists():
                res.update({
                    'product_id': product_id,
                    'product_location_ids': [(6, 0, product.stock_by_locations.ids)],  # Assuming stock_by_locations is a One2many or Many2many field
                })
        
        default_warehouse = self._context.get('default_warehouse')
        if default_warehouse:
            res.update({'def_warehouse': default_warehouse})

        return res
    

    @api.depends('def_warehouse', 'product_location_ids')
    def _compute_qty_def_warehouse(self):
        for wizard in self:
            if wizard.def_warehouse and wizard.product_location_ids:
                warehouse_location = wizard.def_warehouse
                wizard.qty_def_warehouse = sum(
                    line.on_hand_qty for line in wizard.product_location_ids if line.location_id == warehouse_location
                )
            else:
                wizard.qty_def_warehouse = 0.0

    @api.depends('product_location_ids')
    def _compute_total_qty_on_hand(self):
        for wizard in self:
            wizard.total_qty_on_hand = sum(line.on_hand_qty for line in wizard.product_location_ids)
    
