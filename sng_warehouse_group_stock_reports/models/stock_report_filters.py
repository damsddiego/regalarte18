# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SngWarehouseGroupFilterMixin(models.AbstractModel):
    _name = "sng.warehouse.group.filter.mixin"
    _description = "Filtro Reutilizable por Grupo de Almacenes"

    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
        compute="_compute_warehouse_group_id",
        search="_search_warehouse_group_id",
    )

    def _compute_warehouse_group_id(self):
        for record in self:
            record.warehouse_group_id = False

    @api.model
    def _search_warehouse_group_id(self, operator, value):
        if operator == "=":
            group_ids = [value] if value else []
        elif operator == "in":
            group_ids = value
        else:
            raise UserError(
                _("El filtro por grupo de almacenes solo admite los operadores '=' e 'in'.")
            )

        groups = self.env["sng.warehouse.group"].browse(group_ids).exists()
        if not groups:
            return [("id", "=", 0)]
        return self._get_warehouse_group_domain(groups)

    @api.model
    def _get_warehouse_group_domain(self, groups):
        raise NotImplementedError()


class StockQuant(models.Model):
    _name = "stock.quant"
    _inherit = ["stock.quant", "sng.warehouse.group.filter.mixin"]

    @api.model
    def _get_warehouse_group_domain(self, groups):
        return [("location_id", "child_of", groups.warehouse_ids.view_location_id.ids)]


class StockMove(models.Model):
    _name = "stock.move"
    _inherit = ["stock.move", "sng.warehouse.group.filter.mixin"]

    @api.model
    def _get_warehouse_group_domain(self, groups):
        location_ids = groups.warehouse_ids.view_location_id.ids
        return [
            "|",
            ("location_id", "child_of", location_ids),
            ("location_dest_id", "child_of", location_ids),
        ]


class StockMoveLine(models.Model):
    _name = "stock.move.line"
    _inherit = ["stock.move.line", "sng.warehouse.group.filter.mixin"]

    @api.model
    def _get_warehouse_group_domain(self, groups):
        location_ids = groups.warehouse_ids.view_location_id.ids
        return [
            "|",
            ("location_id", "child_of", location_ids),
            ("location_dest_id", "child_of", location_ids),
        ]


class StockValuationLayer(models.Model):
    _name = "stock.valuation.layer"
    _inherit = ["stock.valuation.layer", "sng.warehouse.group.filter.mixin"]

    @api.model
    def _get_warehouse_group_domain(self, groups):
        return [("warehouse_id", "in", groups.warehouse_ids.ids)]
