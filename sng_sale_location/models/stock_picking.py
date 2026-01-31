# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_location_id = fields.Many2one(
        'stock.location',
        string='Ubicación de Venta',
        help='Ubicación definida en la orden de venta',
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Capture location from context when creating picking from sale order"""
        force_location_id = self.env.context.get('force_location_id')
        
        if force_location_id:
            for vals in vals_list:
                # Only set for outgoing pickings (delivery orders)
                if vals.get('picking_type_code') == 'outgoing' or \
                   (vals.get('picking_type_id') and 
                    self.env['stock.picking.type'].browse(vals['picking_type_id']).code == 'outgoing'):
                    vals['sale_location_id'] = force_location_id
        
        pickings = super().create(vals_list)
        
        # Set location on moves after creation
        for picking in pickings:
            if picking.sale_location_id and picking.picking_type_code == 'outgoing':
                picking._update_moves_from_sale_location()
        
        return pickings

    def _update_moves_from_sale_location(self):
        """Update stock moves to use the sale order location"""
        self.ensure_one()
        if self.sale_location_id:
            # Update all moves to use the specified location
            self.move_ids.write({
                'location_id': self.sale_location_id.id,
            })

    def _action_confirm(self):
        """Override to ensure location is set on moves before confirmation"""
        res = super()._action_confirm()
        
        for picking in self:
            if picking.sale_location_id and picking.picking_type_code == 'outgoing':
                picking._update_moves_from_sale_location()
        
        return res
