# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import UserError


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    @api.model_create_multi
    def create(self, vals_list):
        """Crea el almacén y luego genera su tipo de operación RETC."""
        warehouses = super(StockWarehouse, self).create(vals_list)
        for warehouse in warehouses:
            warehouse._create_retc_picking_type()
        return warehouses

    def _create_retc_picking_type(self):
        """Crea el tipo de operación RETC para el almacén actual si no existe."""
        self.ensure_one()
        PickingType = self.env["stock.picking.type"]

        existing = PickingType.search(
            [
                ("sequence_code", "=", "RETC"),
                ("warehouse_id", "=", self.id),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if existing:
            return existing

        customer_location = self.env["stock.location"].search(
            [
                ("usage", "=", "customer"),
                ("company_id", "in", [self.company_id.id, False]),
            ],
            limit=1,
        )
        if not customer_location:
            raise UserError(
                _(
                    "No se encontró la ubicación Partners/Customers necesaria "
                    "para crear el tipo de operación RETC en el almacén %s."
                )
                % self.name
            )

        return PickingType.create(
            {
                "name": f"Retorno de Cliente ({self.name})",
                "code": "internal",
                "sequence_code": "RETC",
                "warehouse_id": self.id,
                "default_location_src_id": customer_location.id,
                "company_id": self.company_id.id,
                "show_operations": False,
                "use_create_lots": False,
                "use_existing_lots": True,
            }
        )
