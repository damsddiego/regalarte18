# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SngWarehouseAvailabilityWizard(models.TransientModel):
    _name = "sng.warehouse.availability.wizard"
    _description = "Wizard Disponibilidad por Almacenes"

    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
        required=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_warehouse_availability_wizard_product_rel",
        "wizard_id",
        "product_id",
        string="Productos",
        domain=[("is_storable", "=", True)],
    )
    product_code = fields.Char(string="Codigo de producto")
    only_available = fields.Boolean(
        string="Solo productos con disponibilidad",
        default=True,
    )
    line_ids = fields.One2many(
        "sng.warehouse.availability.line",
        "wizard_id",
        string="Lineas",
    )

    def _get_warehouses(self):
        self.ensure_one()
        warehouses = self.warehouse_group_id.warehouse_ids.filtered(
            lambda warehouse: warehouse.company_id in self.env.companies
        ).sorted(lambda warehouse: (warehouse.sequence, warehouse.name, warehouse.id))
        if not warehouses:
            raise UserError(
                _(
                    "El grupo seleccionado no contiene almacenes de las companias activas."
                )
            )
        return warehouses

    def _get_product_domain(self):
        self.ensure_one()
        domain = [
            ("active", "=", True),
            ("is_storable", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", self.env.companies.ids),
        ]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.product_code and self.product_code.strip():
            code = self.product_code.strip()
            domain.extend(
                [
                    "|",
                    ("default_code", "ilike", code),
                    ("barcode", "ilike", code),
                ]
            )
        return domain

    def _get_products(self):
        self.ensure_one()
        return self.env["product.product"].search(
            self._get_product_domain(),
            order="default_code, name, id",
        )

    def _get_quantity_by_warehouse(self, products, warehouses):
        self.ensure_one()
        quantities = defaultdict(float)
        if not products or not warehouses:
            return quantities

        grouped_quants = self.env["stock.quant"].read_group(
            [
                ("product_id", "in", products.ids),
                ("location_id", "child_of", warehouses.mapped("lot_stock_id").ids),
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", warehouses.mapped("company_id").ids),
            ],
            ["product_id", "location_id", "quantity:sum", "reserved_quantity:sum"],
            ["product_id", "location_id"],
            lazy=False,
        )
        location_ids = [
            group["location_id"][0]
            for group in grouped_quants
            if group.get("location_id")
        ]
        warehouse_by_location = {
            location.id: location.warehouse_id.id
            for location in self.env["stock.location"].browse(location_ids)
        }
        for group in grouped_quants:
            if not group.get("product_id") or not group.get("location_id"):
                continue
            warehouse_id = warehouse_by_location.get(group["location_id"][0])
            if not warehouse_id:
                continue
            key = (group["product_id"][0], warehouse_id)
            quantities[key] += (group.get("quantity") or 0.0) - (
                group.get("reserved_quantity") or 0.0
            )
        return quantities

    def _get_vendor_map(self, products):
        self.ensure_one()
        if not products:
            return {}

        sellers = self.env["product.supplierinfo"].search(
            [
                ("product_tmpl_id", "in", products.product_tmpl_id.ids),
                "|",
                ("company_id", "=", False),
                ("company_id", "in", self.env.companies.ids),
            ],
            order="sequence, id",
        )
        seller_by_product = {}
        seller_by_template = {}
        for seller in sellers:
            if seller.product_id:
                seller_by_product.setdefault(seller.product_id.id, seller)
            else:
                seller_by_template.setdefault(seller.product_tmpl_id.id, seller)

        result = {}
        for product in products:
            seller = seller_by_product.get(product.id) or seller_by_template.get(
                product.product_tmpl_id.id
            )
            result[product.id] = seller
        return result

    def _get_report_rows(self):
        self.ensure_one()
        warehouses = self._get_warehouses()
        products = self._get_products()
        quantities = self._get_quantity_by_warehouse(products, warehouses)
        vendor_map = self._get_vendor_map(products)
        rows = []

        for product in products:
            seller = vendor_map.get(product.id)
            quantity_by_warehouse = {
                warehouse.id: quantities.get((product.id, warehouse.id), 0.0)
                for warehouse in warehouses
            }
            if self.only_available and not any(
                quantity > 0 for quantity in quantity_by_warehouse.values()
            ):
                continue
            rows.append(
                {
                    "product_id": product.id,
                    "product_code": product.default_code or product.barcode or "",
                    "product_name": product.with_context(
                        display_default_code=False
                    ).display_name,
                    "quantity_by_warehouse": quantity_by_warehouse,
                    "vendor_id": seller.partner_id.id if seller else False,
                    "supplier_name": seller.partner_id.display_name if seller else "",
                }
            )
        return rows

    def _refresh_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        warehouses = self._get_warehouses()
        values_list = []
        for row in self._get_report_rows():
            for warehouse in warehouses:
                values_list.append(
                    {
                        "wizard_id": self.id,
                        "warehouse_group_id": self.warehouse_group_id.id,
                        "warehouse_id": warehouse.id,
                        "product_id": row["product_id"],
                        "product_code": row["product_code"],
                        "product_name": row["product_name"],
                        "vendor_id": row["vendor_id"],
                        "supplier_name": row["supplier_name"],
                        "available_quantity": row["quantity_by_warehouse"].get(
                            warehouse.id, 0.0
                        ),
                    }
                )
        if values_list:
            self.env["sng.warehouse.availability.line"].create(values_list)
        return self.line_ids

    def action_view_report(self):
        self.ensure_one()
        self._refresh_lines()
        action = self.env.ref(
            "sng_warehouse_availability_report.action_sng_warehouse_availability_line"
        ).read()[0]
        action["domain"] = [("wizard_id", "=", self.id)]
        action["context"] = {"default_wizard_id": self.id}
        return action

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref(
            "sng_warehouse_availability_report.action_sng_warehouse_availability_xlsx"
        ).report_action(self)


class SngWarehouseAvailabilityLine(models.TransientModel):
    _name = "sng.warehouse.availability.line"
    _description = "Linea Disponibilidad por Almacen"
    _order = "product_code, product_name, warehouse_id, id"

    wizard_id = fields.Many2one(
        "sng.warehouse.availability.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Almacen",
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
    )
    product_code = fields.Char(string="Codigo", readonly=True)
    product_name = fields.Char(string="Descripcion", readonly=True)
    vendor_id = fields.Many2one("res.partner", string="Proveedor", readonly=True)
    supplier_name = fields.Char(string="Nombre proveedor", readonly=True)
    available_quantity = fields.Float(
        string="Cantidad disponible",
        digits="Product Unit of Measure",
        readonly=True,
    )

    def action_open_product(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "product.product",
            "res_id": self.product_id.id,
            "view_mode": "form",
            "target": "current",
        }
