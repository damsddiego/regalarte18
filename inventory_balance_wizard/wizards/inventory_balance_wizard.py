# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InventoryBalanceWizard(models.TransientModel):
    _name = "inventory.balance.wizard"
    _description = "Wizard - Inventario por filtros (Paso 1)"

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacén",
        help="Si eliges almacén y no eliges ubicaciones, se usará su ubicación principal de existencias.",
    )
    location_ids = fields.Many2many(
        "stock.location",
        string="Ubicaciones",
        domain=[("usage", "=", "internal"), ("active", "=", True)],
        help="Ubicaciones internas donde quieres consultar stock.",
    )
    include_child_locations = fields.Boolean(
        string="Incluir sub-ubicaciones",
        default=True,
        help="Si está activo, incluye ubicaciones hijas dentro de las seleccionadas.",
    )

    product_ids = fields.Many2many(
        "product.product",
        string="Productos",
        domain=[("type", "in", ["consu"])],
    )
    categ_ids = fields.Many2many(
        "product.category",
        string="Categorías",
        help="Filtra por categorías. Si seleccionas categorías, se incluirán sus subcategorías.",
    )

    only_positive_qty = fields.Boolean(
        string="Solo con stock disponible",
        default=True,
        help="Si está activo, muestra solo quants con cantidad > 0.",
    )

    show_first_in = fields.Boolean(string="Mostrar primer ingreso", default=False)
    show_last_in = fields.Boolean(string="Mostrar último ingreso", default=False)

    group_by_product = fields.Boolean(string="Agrupar por producto", default=True)
    group_by_location = fields.Boolean(string="Agrupar por ubicación", default=True)

    @api.constrains("warehouse_id", "location_ids")
    def _check_warehouse_or_location(self):
        for wiz in self:
            if not wiz.warehouse_id and not wiz.location_ids:
                raise UserError(_("Debes seleccionar un almacén o al menos una ubicación."))

    def _get_effective_locations(self):
        """Retorna IDs de ubicaciones a usar según almacén/ubicaciones + include_child."""
        self.ensure_one()
        Location = self.env["stock.location"]

        base_locations = self.location_ids
        if not base_locations:
            if not self.warehouse_id:
                raise UserError(_("Debes seleccionar un almacén o al menos una ubicación."))
            base_locations = self.warehouse_id.lot_stock_id

        if not base_locations:
            raise UserError(_("No se pudieron determinar ubicaciones a consultar."))

        if self.include_child_locations:
            return Location.search([("id", "child_of", base_locations.ids)]).ids

        return base_locations.ids

    def _get_quant_domain(self):
        self.ensure_one()

        location_ids = self._get_effective_locations()
        domain = [
            ("location_id", "in", location_ids),
        ]

        if self.only_positive_qty:
            domain.append(("quantity", ">", 0))

        if self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))

        if self.categ_ids:
            # incluir subcategorías con child_of
            domain.append(("product_id.product_tmpl_id.categ_id", "child_of", self.categ_ids.ids))

        return domain

    def action_open_quants(self):
        self.ensure_one()
        domain = self._get_quant_domain()

        ctx = dict(self.env.context or {})
        groupbys = []
        if self.group_by_product:
            groupbys.append("product_id")
        if self.group_by_location:
            groupbys.append("location_id")
        if groupbys:
            ctx["group_by"] = groupbys

        return {
            "type": "ir.actions.act_window",
            "name": _("Inventario (Filtrado)"),
            "res_model": "stock.quant",
            "view_mode": "list,pivot,graph,form",
            "domain": domain,
            "context": ctx,
            "target": "current",
        }

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref(
            "inventory_balance_wizard.action_inventory_balance_xlsx"
        ).report_action(self)
