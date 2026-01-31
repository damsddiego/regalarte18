# -*- coding: utf-8 -*-
from odoo import models, api


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self):
        """Override to force reservation from sale order location only"""
        # Filter moves by those with sale location restriction
        restricted_moves = self.filtered(
            lambda m: m.picking_id.sale_location_id and
                     m.picking_id.picking_type_code == 'outgoing'
        )
        unrestricted_moves = self - restricted_moves

        # Ensure source location is set for restricted moves before processing
        for move in restricted_moves:
            if move.location_id != move.picking_id.sale_location_id:
                move.location_id = move.picking_id.sale_location_id

        # Process all moves through super - the _update_reserved_quantity override
        # will handle the location restriction
        return super()._action_assign()

    def _update_reserved_quantity(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        """Override to ensure reservation only from sale location"""
        self.ensure_one()

        # Check if we have a sale location restriction
        if self.picking_id and self.picking_id.sale_location_id and self.picking_id.picking_type_code == 'outgoing':
            # Only allow reservation from the specified location
            if location_id != self.picking_id.sale_location_id:
                # Don't reserve from other locations
                return 0

        return super()._update_reserved_quantity(
            need, location_id,
            lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict
        )

    def _get_available_quantity(self, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
        """Override to filter available quantity by sale location"""
        self.ensure_one()

        # Check if we have a sale location restriction
        if self.picking_id and self.picking_id.sale_location_id and self.picking_id.picking_type_code == 'outgoing':
            if location_id != self.picking_id.sale_location_id:
                # Return 0 for locations that don't match
                return 0

        return super()._get_available_quantity(
            location_id, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict, allow_negative=allow_negative
        )
