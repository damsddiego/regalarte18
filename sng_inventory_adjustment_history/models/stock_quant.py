# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools import float_is_zero


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _sng_get_adjustment_unit_cost(self):
        self.ensure_one()
        product = self.product_id.with_company(self.company_id)
        if product.lot_valuated and self.lot_id:
            return self.lot_id.with_company(self.company_id).standard_price
        return product.standard_price

    def _sng_prepare_adjustment_history_vals(self, warehouse_groups):
        self.ensure_one()
        unit_cost = self._sng_get_adjustment_unit_cost()
        adjusted_quantity = self.inventory_quantity - self.quantity
        return {
            "adjustment_date": fields.Datetime.now(),
            "product_id": self.product_id.id,
            "location_id": self.location_id.id,
            "warehouse_id": self.location_id.warehouse_id.id,
            "warehouse_group_ids": [(6, 0, warehouse_groups.ids)],
            "quant_id": self.id,
            "lot_id": self.lot_id.id,
            "package_id": self.package_id.id,
            "owner_id": self.owner_id.id,
            "uom_id": self.product_uom_id.id,
            "previous_quantity": self.quantity,
            "adjusted_quantity": adjusted_quantity,
            "new_quantity": self.inventory_quantity,
            "adjusted_by_id": self.env.user.id,
            "counted_by_id": self.user_id.id,
            "unit_cost": unit_cost,
            "adjustment_cost": adjusted_quantity * unit_cost,
            "company_id": self.company_id.id or self.env.company.id,
        }

    def _apply_inventory(self):
        grouped_quants = self.filtered("location_id.warehouse_id")
        groups_by_warehouse = {}
        if grouped_quants:
            groups = self.env["sng.warehouse.group"].search(
                [("warehouse_ids", "in", grouped_quants.location_id.warehouse_id.ids)]
            )
            for warehouse in grouped_quants.location_id.warehouse_id:
                groups_by_warehouse[warehouse.id] = groups.filtered(
                    lambda group, warehouse=warehouse: warehouse in group.warehouse_ids
                )

        history_model = self.env["sng.inventory.adjustment.history"].sudo()
        histories_by_quant = {}
        for quant in self:
            warehouse_groups = groups_by_warehouse.get(quant.location_id.warehouse_id.id)
            if not warehouse_groups:
                continue
            history = history_model.create(
                quant._sng_prepare_adjustment_history_vals(warehouse_groups)
            )
            histories_by_quant[quant.id] = history.id

        self = self.with_context(
            sng_inventory_adjustment_histories=histories_by_quant
        )
        result = super()._apply_inventory()

        histories = history_model.browse(list(histories_by_quant.values()))
        for history in histories:
            valuation_layers = history.move_ids.sudo().stock_valuation_layer_ids
            if not valuation_layers:
                continue
            valuation_quantity = sum(valuation_layers.mapped("quantity"))
            valuation_value = sum(valuation_layers.mapped("value"))
            unit_cost = history.unit_cost
            if not float_is_zero(
                valuation_quantity,
                precision_rounding=history.uom_id.rounding,
            ):
                unit_cost = abs(valuation_value / valuation_quantity)
            history.write(
                {
                    "unit_cost": unit_cost,
                    "adjustment_cost": valuation_value,
                }
            )
        histories._sng_send_adjustment_notifications()
        return result

    def _get_inventory_move_values(
        self,
        qty,
        location_id,
        location_dest_id,
        package_id=False,
        package_dest_id=False,
    ):
        values = super()._get_inventory_move_values(
            qty,
            location_id,
            location_dest_id,
            package_id=package_id,
            package_dest_id=package_dest_id,
        )
        history_id = self.env.context.get(
            "sng_inventory_adjustment_histories", {}
        ).get(self.id)
        if history_id:
            values["sng_inventory_adjustment_history_id"] = history_id
        return values
