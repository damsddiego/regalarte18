# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación de Origen',
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False]), ('active', '=', True)]",
        help='Ubicación interna desde donde se tomará el stock para esta orden de venta',
        tracking=True,
        copy=False,
    )

    @api.onchange('partner_id')
    def _onchange_partner_id_location(self):
        """Set location_id from partner's sale_location_id when partner is selected"""
        if self.partner_id and self.partner_id.sale_location_id:
            self.location_id = self.partner_id.sale_location_id

    @api.constrains('location_id', 'order_line')
    def _check_location_required(self):
        """Ensure location is selected when order has lines"""
        for order in self:
            if order.order_line and not order.location_id and order.state in ('sale', 'done'):
                raise ValidationError(_('Debe seleccionar una ubicación de origen antes de confirmar la orden.'))

    def _check_location_stock_availability(self):
        """
        Validate that sufficient stock is available at the selected location
        for all order lines before confirmation.
        """
        self.ensure_one()
        
        if not self.location_id:
            raise UserError(_('Debe seleccionar una ubicación de origen antes de confirmar la orden.'))
        
        # Get warehouse to filter stock correctly
        warehouse = self.warehouse_id
        
        stock_errors = []
        
        for line in self.order_line:
            # Skip non-stockable products and services
            if line.product_id.type not in ('product', 'consu'):
                continue
            
            # Skip lines with no quantity
            if line.product_uom_qty <= 0:
                continue
            
            product = line.product_id
            required_qty = line.product_uom_qty
            
            # Convert to product UoM if needed
            if line.product_uom != product.uom_id:
                required_qty = line.product_uom._compute_quantity(
                    required_qty, 
                    product.uom_id
                )
            
            # Get available quantity at the selected location
            available_qty = self.env['stock.quant']._get_available_quantity(
                product,
                self.location_id,
                allow_negative=False
            )
            
            if available_qty < required_qty:
                stock_errors.append(
                    _('• %(product)s: Requerido %(required).2f, Disponible %(available).2f en %(location)s',
                      product=product.display_name,
                      required=required_qty,
                      available=available_qty,
                      location=self.location_id.complete_name)
                )
        
        if stock_errors:
            error_msg = _('Stock insuficiente en la ubicación seleccionada:\n\n%s\n\n'
                         'Por favor, seleccione otra ubicación o ajuste las cantidades.') % '\n'.join(stock_errors)
            raise UserError(error_msg)
        
        return True

    def action_confirm(self):
        """Override to validate stock availability at selected location before confirmation"""
        for order in self:
            # Only validate for orders with physical products
            has_stockable_products = any(
                line.product_id.type in ('product', 'consu') and line.product_uom_qty > 0
                for line in order.order_line
            )
            
            if has_stockable_products:
                order._check_location_stock_availability()
        
        # Call super with context to pass location to picking
        return super(SaleOrder, self.with_context(
            force_location_id=self.location_id.id if self.location_id else False
        )).action_confirm()

    def _prepare_procurement_group_vals(self):
        """Add location context to procurement group"""
        vals = super()._prepare_procurement_group_vals()
        if self.location_id:
            # Store location in procurement group for later use
            if 'move_dest_ids' not in vals:
                vals['move_dest_ids'] = []
        return vals
