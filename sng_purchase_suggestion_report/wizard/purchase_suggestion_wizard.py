# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# El sistema inicio operaciones en abril 2026: los meses anteriores no
# tienen ventas registradas y no deben diluir el promedio mensual.
SNG_OPERATIONS_START_DATE = date(2026, 4, 1)


class SngPurchaseSuggestionWizard(models.TransientModel):
    _name = "sng.purchase.suggestion.wizard"
    _description = "Wizard Reporte Sugerido de Compras"

    date_from = fields.Date(
        string="Fecha desde",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Fecha hasta",
        required=True,
        default=fields.Date.context_today,
    )
    coverage_days = fields.Integer(
        string="Dias de cobertura",
        required=True,
        default=30,
    )
    company_ids = fields.Many2many(
        "res.company",
        string="Companias",
        default=lambda self: self.env.companies,
    )
    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Almacenes",
    )
    location_ids = fields.Many2many(
        "stock.location",
        string="Bodegas",
        domain=[("usage", "=", "internal")],
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_purchase_suggestion_wizard_product_rel",
        "wizard_id",
        "product_id",
        string="Productos",
        domain=[("purchase_ok", "=", True), ("is_storable", "=", True)],
    )
    product_code = fields.Char(string="Codigo de producto")
    only_with_sales = fields.Boolean(string="Solo con ventas", default=False)
    outlier_threshold = fields.Float(
        string="Umbral desviacion estandar (σ)",
        default=2.0,
        required=True,
        help="Un producto se marca como venta atipica cuando su promedio mensual actual supera el promedio historico mas este numero de desviaciones estandar.",
    )
    min_history_months = fields.Integer(
        string="Meses minimos con ventas",
        default=2,
        required=True,
        help="Minimo de meses historicos con ventas para poder calcular la desviacion estandar.",
    )
    line_ids = fields.One2many(
        "sng.purchase.suggestion.line",
        "wizard_id",
        string="Lineas",
    )

    @api.constrains("date_from", "date_to", "coverage_days")
    def _check_filters(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("La fecha inicial no puede ser mayor que la fecha final."))
            if wizard.coverage_days < 0:
                raise ValidationError(_("Los dias de cobertura no pueden ser negativos."))

    @api.constrains("outlier_threshold", "min_history_months")
    def _check_outlier_config(self):
        for wizard in self:
            if wizard.outlier_threshold < 0:
                raise ValidationError(_("El umbral de desviacion estandar no puede ser negativo."))
            if wizard.min_history_months < 2:
                raise ValidationError(_("Se requieren al menos 2 meses con ventas para calcular la desviacion estandar."))

    def _get_selected_company_ids(self):
        self.ensure_one()
        return self.company_ids.ids or self.env.companies.ids or [self.env.company.id]

    def _get_selected_warehouses(self):
        self.ensure_one()
        warehouses = self.warehouse_group_id.warehouse_ids or self.warehouse_ids
        company_ids = self._get_selected_company_ids()
        return warehouses.filtered(lambda warehouse: warehouse.company_id.id in company_ids)

    @api.onchange("warehouse_group_id")
    def _onchange_warehouse_group_id(self):
        for wizard in self:
            if wizard.warehouse_group_id:
                wizard.warehouse_ids = wizard.warehouse_group_id.warehouse_ids

    def _get_analysis_days(self):
        self.ensure_one()
        return max((self.date_to - self.date_from).days + 1, 1)

    def _get_avg_calculation_days(self):
        """Dias usados para promediar las ventas mensuales.

        Recorta el inicio del periodo a la fecha de inicio de operaciones
        del sistema (SNG_OPERATIONS_START_DATE) para que los meses sin
        datos no diluyan el promedio mensual.
        """
        self.ensure_one()
        date_from = max(self.date_from, SNG_OPERATIONS_START_DATE)
        return max((self.date_to - date_from).days + 1, 1)

    def _get_product_domain(self):
        self.ensure_one()
        company_ids = self._get_selected_company_ids()
        domain = [
            ("purchase_ok", "=", True),
            ("is_storable", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", company_ids),
        ]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.product_code:
            code = self.product_code.strip()
            if not code:
                return domain
            domain.extend(["|", ("default_code", "ilike", code), ("barcode", "ilike", code)])
        return domain

    def _get_report_products(self):
        self.ensure_one()
        return self.env["product.product"].search(self._get_product_domain(), order="default_code, name, id")

    def _get_sales_location_ids(self):
        self.ensure_one()
        if not self.location_ids:
            return []
        return self.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("id", "child_of", self.location_ids.ids),
            ]
        ).ids

    def _get_sales_qty_map(self, product_ids):
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        query = """
            SELECT
                aml.product_id,
                COALESCE(
                    SUM(
                        CASE
                            WHEN am.move_type = 'out_refund' THEN -aml.quantity
                            ELSE aml.quantity
                        END
                    ),
                    0.0
                ) AS qty_sold
            FROM account_move_line aml
            JOIN account_move am
                ON am.id = aml.move_id
            LEFT JOIN res_partner rp
                ON rp.id = am.partner_id
            LEFT JOIN LATERAL (
                SELECT
                    sol.id AS sale_line_id,
                    sol.order_id AS order_id
                FROM sale_order_line_invoice_rel rel
                JOIN sale_order_line sol
                    ON sol.id = rel.order_line_id
                WHERE rel.invoice_line_id = aml.id
                ORDER BY sol.id
                LIMIT 1
            ) sale_link ON TRUE
            LEFT JOIN sale_order so
                ON so.id = sale_link.order_id
            LEFT JOIN LATERAL (
                SELECT
                    sp2.id AS picking_id,
                    sm.partner_sale_location_id AS partner_sale_location_id
                FROM stock_move sm
                JOIN stock_picking sp2
                    ON sp2.id = sm.picking_id
                JOIN stock_picking_type spt2
                    ON spt2.id = sp2.picking_type_id
                WHERE sm.sale_line_id = sale_link.sale_line_id
                  AND spt2.code = 'outgoing'
                ORDER BY COALESCE(sp2.date_done, sp2.scheduled_date) DESC, sp2.id DESC
                LIMIT 1
            ) picking_link ON TRUE
            LEFT JOIN stock_picking sp
                ON sp.id = picking_link.picking_id
            LEFT JOIN stock_picking_type spt
                ON spt.id = sp.picking_type_id
            WHERE am.state = 'posted'
              AND am.move_type IN ('out_invoice', 'out_refund')
              AND aml.display_type = 'product'
              AND aml.product_id = ANY(%s)
              AND COALESCE(am.invoice_date, am.date) >= %s
              AND COALESCE(am.invoice_date, am.date) <= %s
              AND am.company_id = ANY(%s)
        """
        params = [product_ids, self.date_from, self.date_to, company_ids]

        if warehouses:
            query += " AND COALESCE(so.warehouse_id, spt.warehouse_id) = ANY(%s)"
            params.append(warehouses.ids)

        sales_location_ids = self._get_sales_location_ids()
        if sales_location_ids:
            query += """
                AND COALESCE(
                    so.partner_sale_location_id,
                    picking_link.partner_sale_location_id,
                    rp.sale_location_id
                ) = ANY(%s)
            """
            params.append(sales_location_ids)

        query += " GROUP BY aml.product_id"
        self.env.cr.execute(query, params)
        return {product_id: qty_sold for product_id, qty_sold in self.env.cr.fetchall()}

    def _get_monthly_sales_history_map(self, product_ids):
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        query = """
            SELECT
                aml.product_id,
                DATE_TRUNC('month', COALESCE(am.invoice_date, am.date)) AS month,
                COALESCE(
                    SUM(
                        CASE
                            WHEN am.move_type = 'out_refund' THEN -aml.quantity
                            ELSE aml.quantity
                        END
                    ),
                    0.0
                ) AS qty_sold
            FROM account_move_line aml
            JOIN account_move am
                ON am.id = aml.move_id
            LEFT JOIN res_partner rp
                ON rp.id = am.partner_id
            LEFT JOIN LATERAL (
                SELECT
                    sol.id AS sale_line_id,
                    sol.order_id AS order_id
                FROM sale_order_line_invoice_rel rel
                JOIN sale_order_line sol
                    ON sol.id = rel.order_line_id
                WHERE rel.invoice_line_id = aml.id
                ORDER BY sol.id
                LIMIT 1
            ) sale_link ON TRUE
            LEFT JOIN sale_order so
                ON so.id = sale_link.order_id
            LEFT JOIN LATERAL (
                SELECT
                    sp2.id AS picking_id,
                    sm.partner_sale_location_id AS partner_sale_location_id
                FROM stock_move sm
                JOIN stock_picking sp2
                    ON sp2.id = sm.picking_id
                JOIN stock_picking_type spt2
                    ON spt2.id = sp2.picking_type_id
                WHERE sm.sale_line_id = sale_link.sale_line_id
                  AND spt2.code = 'outgoing'
                ORDER BY COALESCE(sp2.date_done, sp2.scheduled_date) DESC, sp2.id DESC
                LIMIT 1
            ) picking_link ON TRUE
            LEFT JOIN stock_picking sp
                ON sp.id = picking_link.picking_id
            LEFT JOIN stock_picking_type spt
                ON spt.id = sp.picking_type_id
            WHERE am.state = 'posted'
              AND am.move_type IN ('out_invoice', 'out_refund')
              AND aml.display_type = 'product'
              AND aml.product_id = ANY(%s)
              AND COALESCE(am.invoice_date, am.date) >= %s
              AND COALESCE(am.invoice_date, am.date) < %s
              AND am.company_id = ANY(%s)
        """
        params = [
            product_ids,
            SNG_OPERATIONS_START_DATE,
            self.date_from,
            company_ids,
        ]

        if warehouses:
            query += " AND COALESCE(so.warehouse_id, spt.warehouse_id) = ANY(%s)"
            params.append(warehouses.ids)

        sales_location_ids = self._get_sales_location_ids()
        if sales_location_ids:
            query += """
                AND COALESCE(
                    so.partner_sale_location_id,
                    picking_link.partner_sale_location_id,
                    rp.sale_location_id
                ) = ANY(%s)
            """
            params.append(sales_location_ids)

        query += " GROUP BY aml.product_id, DATE_TRUNC('month', COALESCE(am.invoice_date, am.date))"
        self.env.cr.execute(query, params)

        history = defaultdict(list)
        for product_id, _month, qty_sold in self.env.cr.fetchall():
            history[product_id].append(qty_sold)
        return dict(history)

    def _is_product_outlier(self, product_id, current_avg, history_map):
        self.ensure_one()
        values = history_map.get(product_id, [])
        if len(values) < max(2, self.min_history_months):
            return False
        mean = sum(values) / len(values)
        if len(values) == 1:
            return current_avg > mean
        variance = sum((qty - mean) ** 2 for qty in values) / (len(values) - 1)
        std = variance ** 0.5
        if std == 0:
            return current_avg > mean
        return current_avg > mean + (self.outlier_threshold * std)

    def _get_purchase_qty_map(self, product_ids):
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        query = """
            SELECT
                pol.product_id,
                SUM(pol.product_qty - pol.qty_received) AS qty_in_purchase
            FROM purchase_order_line pol
            JOIN purchase_order po ON po.id = pol.order_id
            JOIN stock_picking_type spt ON spt.id = po.picking_type_id
            WHERE po.state IN ('purchase', 'done')
              AND pol.qty_received < pol.product_qty
              AND pol.product_id = ANY(%s)
              AND po.company_id = ANY(%s)
        """
        params = [product_ids, company_ids]

        if warehouses:
            query += " AND spt.warehouse_id = ANY(%s)"
            params.append(warehouses.ids)

        query += " GROUP BY pol.product_id"
        self.env.cr.execute(query, params)
        return {product_id: qty for product_id, qty in self.env.cr.fetchall()}

    def _get_stock_qty_map(self, product_ids):
        self.ensure_one()
        if not product_ids:
            return {}

        company_ids = self._get_selected_company_ids()
        warehouses = self._get_selected_warehouses()
        domain = [
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
            ("company_id", "in", company_ids),
        ]
        if warehouses:
            domain.append(("location_id", "child_of", warehouses.mapped("lot_stock_id").ids))
        if self.location_ids:
            domain.append(("location_id", "child_of", self.location_ids.ids))

        grouped = self.env["stock.quant"].read_group(
            domain,
            ["product_id", "quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        return {
            item["product_id"][0]: item["quantity"]
            for item in grouped
            if item.get("product_id")
        }

    def _get_vendor_map(self, products):
        self.ensure_one()
        company_ids = set(self._get_selected_company_ids())
        vendor_map = {}
        for product in products:
            sellers = product.seller_ids.filtered(
                lambda seller: not seller.company_id or seller.company_id.id in company_ids
            )
            seller = sellers.sorted(lambda rec: (rec.sequence, rec.min_qty or 0.0, rec.id))[:1]
            vendor_map[product.id] = seller[:1]
        return vendor_map

    def _get_product_report_name(self, product):
        self.ensure_one()
        return product.with_context(display_default_code=False).display_name

    def _get_report_rows(self):
        self.ensure_one()
        products = self._get_report_products()
        if not products:
            return []

        product_ids = products.ids
        analysis_days = self._get_analysis_days()
        avg_calculation_months = self._get_avg_calculation_days() / 30.0
        sales_map = self._get_sales_qty_map(product_ids)
        stock_map = self._get_stock_qty_map(product_ids)
        purchase_map = self._get_purchase_qty_map(product_ids)
        history_map = self._get_monthly_sales_history_map(product_ids)
        vendor_map = self._get_vendor_map(products)
        rows = []

        for product in products:
            qty_sold = sales_map.get(product.id, 0.0)
            qty_on_hand = stock_map.get(product.id, 0.0)
            qty_in_purchase = purchase_map.get(product.id, 0.0)
            avg_monthly_sales = qty_sold / avg_calculation_months
            is_outlier = self._is_product_outlier(product.id, avg_monthly_sales, history_map)
            suggested_purchase_qty = avg_monthly_sales * (self.coverage_days / 30.0)
            qty_to_buy = suggested_purchase_qty - qty_on_hand - qty_in_purchase
            seller = vendor_map.get(product.id)
            rows.append(
                {
                    "wizard_id": self.id,
                    "product_id": product.id,
                    "product_name": self._get_product_report_name(product),
                    "product_code": product.default_code or product.barcode or "",
                    "vendor_id": seller.partner_id.id if seller else False,
                    "supplier_name": seller.partner_id.display_name if seller else "",
                    "qty_on_hand": qty_on_hand,
                    "qty_in_purchase": qty_in_purchase,
                    "qty_sold": qty_sold,
                    "analysis_days": analysis_days,
                    "coverage_days": self.coverage_days,
                    "avg_monthly_sales": avg_monthly_sales,
                    "is_outlier": is_outlier,
                    "suggested_purchase_qty": suggested_purchase_qty,
                    "qty_to_buy": qty_to_buy,
                }
            )
        if self.only_with_sales:
            rows = [r for r in rows if r["qty_sold"] > 0]
        return rows

    def _refresh_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        rows = self._get_report_rows()
        if rows:
            self.env["sng.purchase.suggestion.line"].create(rows)
        return rows

    def _get_filter_summary(self):
        self.ensure_one()
        warehouses = self._get_selected_warehouses()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "analysis_days": self._get_analysis_days(),
            "coverage_days": self.coverage_days,
            "companies": ", ".join(self.company_ids.mapped("display_name")) or _("Todas"),
            "warehouse_group": self.warehouse_group_id.display_name or _("Ninguno"),
            "warehouses": ", ".join(warehouses.mapped("display_name")) or _("Todos"),
            "locations": ", ".join(self.location_ids.mapped("display_name")) or _("Todas"),
            "products": ", ".join(self.product_ids.mapped("display_name")) or _("Todos"),
            "product_code": self.product_code or _("Todos"),
        }

    def action_view_report(self):
        self.ensure_one()
        self._refresh_lines()
        action = self.env.ref("sng_purchase_suggestion_report.action_sng_purchase_suggestion_line").read()[0]
        action["domain"] = [("wizard_id", "=", self.id)]
        action["context"] = {"default_wizard_id": self.id}
        return action

    def action_export_xlsx(self):
        self.ensure_one()
        self._refresh_lines()
        return self.env.ref("sng_purchase_suggestion_report.action_sng_purchase_suggestion_xlsx").report_action(self)


class SngPurchaseSuggestionLine(models.TransientModel):
    _name = "sng.purchase.suggestion.line"
    _description = "Linea Reporte Sugerido de Compras"
    _order = "qty_to_buy desc, qty_sold desc, product_name asc, id asc"

    wizard_id = fields.Many2one(
        "sng.purchase.suggestion.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        readonly=True,
    )
    product_name = fields.Char(string="Nombre del producto", readonly=True)
    product_code = fields.Char(string="Codigo de articulo", readonly=True)
    vendor_id = fields.Many2one("res.partner", string="Proveedor sugerido", readonly=True)
    supplier_name = fields.Char(string="Proveedor", readonly=True)
    qty_on_hand = fields.Float(
        string="Existencia actual",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_in_purchase = fields.Float(
        string="En ordenes de compra",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_sold = fields.Float(
        string="Cantidad total vendida",
        digits="Product Unit of Measure",
        readonly=True,
    )
    analysis_days = fields.Integer(string="Dias analizados", readonly=True)
    coverage_days = fields.Integer(string="Dias de cobertura", readonly=True)
    avg_monthly_sales = fields.Float(
        string="Promedio de venta mensual",
        digits="Product Unit of Measure",
        readonly=True,
    )
    is_outlier = fields.Boolean(
        string="Venta atipica",
        readonly=True,
    )
    suggested_purchase_qty = fields.Float(
        string="Sugerido de compra",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_to_buy = fields.Float(
        string="Sugerido menos existencias",
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
