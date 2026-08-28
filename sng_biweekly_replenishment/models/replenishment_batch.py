# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round


class SngBiweeklyReplenishmentBatch(models.Model):
    _name = "sng.biweekly.replenishment.batch"
    _description = "Ciclo de Reabastecimiento Bisemanal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "run_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default=lambda self: _("Nuevo"),
        readonly=True,
        index=True,
    )
    config_id = fields.Many2one(
        "sng.biweekly.replenishment.config",
        string="Configuración",
        required=True,
        ondelete="restrict",
        check_company=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="config_id.company_id",
        store=True,
        index=True,
    )
    main_warehouse_id = fields.Many2one(
        related="config_id.main_warehouse_id",
        store=True,
        string="Bodega Principal",
    )
    run_date = fields.Date(
        string="Fecha del ciclo",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    period_start = fields.Datetime(
        string="Inicio de demanda",
        required=True,
        readonly=True,
    )
    period_end = fields.Datetime(
        string="Fin de demanda",
        required=True,
        readonly=True,
    )
    generated_at = fields.Datetime(
        string="Transferencias generadas",
        readonly=True,
        copy=False,
    )
    cancelled = fields.Boolean(default=False, readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("generated", "Generado"),
            ("partial", "Con faltantes"),
            ("progress", "En proceso"),
            ("done", "Completado"),
            ("cancel", "Cancelado"),
        ],
        string="Estado",
        compute="_compute_state",
        store=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "sng.biweekly.replenishment.line",
        "batch_id",
        string="SKUs",
        copy=False,
    )
    allocation_ids = fields.One2many(
        "sng.biweekly.replenishment.allocation",
        "batch_id",
        string="Asignaciones",
        copy=False,
    )
    picking_ids = fields.One2many(
        "stock.picking",
        "sng_replenishment_batch_id",
        string="Transferencias",
        copy=False,
    )
    picking_count = fields.Integer(compute="_compute_counts")
    line_count = fields.Integer(compute="_compute_counts")
    total_demand_qty = fields.Float(
        string="Demanda total",
        compute="_compute_totals",
        digits="Product Unit of Measure",
    )
    total_suggested_qty = fields.Float(
        string="Sugerido total",
        compute="_compute_totals",
        digits="Product Unit of Measure",
    )
    total_allocated_qty = fields.Float(
        string="Asignado total",
        compute="_compute_totals",
        digits="Product Unit of Measure",
    )
    total_shortage_qty = fields.Float(
        string="Faltante total",
        compute="_compute_totals",
        digits="Product Unit of Measure",
    )

    _sql_constraints = [
        (
            "config_run_date_unique",
            "unique(config_id, run_date)",
            "Ya existe un ciclo para esta configuración y fecha.",
        ),
        (
            "period_dates_valid",
            "check(period_start < period_end)",
            "El inicio del período debe ser anterior al final.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo")) == _("Nuevo"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "sng.biweekly.replenishment.batch"
                ) or _("Nuevo")
        return super().create(vals_list)

    @api.depends(
        "cancelled",
        "generated_at",
        "picking_ids.state",
        "line_ids.shortage_qty",
    )
    def _compute_state(self):
        for batch in self:
            if batch.cancelled:
                batch.state = "cancel"
                continue
            if not batch.generated_at:
                batch.state = "draft"
                continue
            if any(line.shortage_qty > 0 for line in batch.line_ids):
                batch.state = "partial"
                continue
            active_pickings = batch.picking_ids.filtered(lambda p: p.state != "cancel")
            if active_pickings and all(p.state == "done" for p in active_pickings):
                batch.state = "done"
            elif any(p.state not in ("draft", "cancel") for p in batch.picking_ids):
                batch.state = "progress"
            else:
                batch.state = "generated"

    @api.depends("picking_ids", "line_ids")
    def _compute_counts(self):
        for batch in self:
            batch.picking_count = len(batch.picking_ids)
            batch.line_count = len(batch.line_ids)

    @api.depends(
        "line_ids.demand_qty",
        "line_ids.suggested_qty",
        "line_ids.allocated_qty",
        "line_ids.shortage_qty",
    )
    def _compute_totals(self):
        for batch in self:
            batch.total_demand_qty = sum(batch.line_ids.mapped("demand_qty"))
            batch.total_suggested_qty = sum(batch.line_ids.mapped("suggested_qty"))
            batch.total_allocated_qty = sum(batch.line_ids.mapped("allocated_qty"))
            batch.total_shortage_qty = sum(batch.line_ids.mapped("shortage_qty"))

    def _get_form_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ciclo de reabastecimiento"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_recalculate(self):
        self.ensure_one()
        if self.cancelled:
            raise UserError(_("No puede recalcular un ciclo cancelado."))
        if self.picking_ids:
            raise UserError(
                _(
                    "El ciclo ya tiene transferencias. Cancélelo y genere un nuevo ciclo "
                    "para conservar la trazabilidad."
                )
            )
        self.allocation_ids.unlink()
        self.line_ids.unlink()
        self.generated_at = False

        config = self.config_id
        demand_map = config._get_demand_by_product(self.period_start, self.period_end)
        positive_product_ids = [
            product_id for product_id, qty in demand_map.items() if qty > 0
        ]
        products = self.env["product.product"].browse(positive_product_ids).exists()
        if not products:
            self.message_post(body=_("No se encontraron salidas físicas en el período."))
            return self._get_form_action()

        main_quantities = config._get_quantity_map(products, config.main_warehouse_id)
        draft_in = config._get_open_draft_quantity(
            products, config.main_warehouse_id, "in"
        )
        draft_out = config._get_open_draft_quantity(
            products, config.main_warehouse_id, "out"
        )
        line_values = []
        for product in products.sorted(lambda p: (p.default_code or "", p.name, p.id)):
            demand_qty = demand_map.get(product.id, 0.0)
            daily_demand = demand_qty / config.demand_window_days
            target_stock = float_round(
                daily_demand * (config.coverage_days + config.safety_days),
                precision_rounding=product.uom_id.rounding,
                rounding_method="UP",
            )
            reorder_point = float_round(
                daily_demand * (config.lead_time_days + config.safety_days),
                precision_rounding=product.uom_id.rounding,
                rounding_method="UP",
            )
            quantity_values = main_quantities.get(product.id, {})
            free_qty = quantity_values.get("free_qty", 0.0)
            forecast_qty = quantity_values.get("virtual_available", 0.0)
            draft_in_qty = draft_in.get(product.id, 0.0)
            draft_out_qty = draft_out.get(product.id, 0.0)
            projected_qty = forecast_qty + draft_in_qty - draft_out_qty
            suggested_qty = float_round(
                max(0.0, target_stock - projected_qty),
                precision_rounding=product.uom_id.rounding,
                rounding_method="UP",
            )
            line_values.append(
                {
                    "batch_id": self.id,
                    "product_id": product.id,
                    "uom_id": product.uom_id.id,
                    "demand_qty": demand_qty,
                    "daily_demand": daily_demand,
                    "coverage_days": config.coverage_days,
                    "safety_days": config.safety_days,
                    "lead_time_days": config.lead_time_days,
                    "target_stock": target_stock,
                    "reorder_point": reorder_point,
                    "free_qty": free_qty,
                    "forecast_qty": forecast_qty,
                    "draft_in_qty": draft_in_qty,
                    "draft_out_qty": draft_out_qty,
                    "projected_qty": projected_qty,
                    "suggested_qty": suggested_qty,
                }
            )
        lines = self.env["sng.biweekly.replenishment.line"].create(line_values)
        self._allocate_sources(lines.filtered(lambda line: line.suggested_qty > 0))
        self.message_post(
            body=_(
                "Cálculo actualizado con %(products)s SKU(s) y demanda desde "
                "%(start)s hasta %(end)s.",
                products=len(lines),
                start=fields.Datetime.to_string(self.period_start),
                end=fields.Datetime.to_string(self.period_end),
            )
        )
        return self._get_form_action()

    def _allocate_sources(self, lines):
        self.ensure_one()
        if not lines:
            return
        products = lines.mapped("product_id")
        source_lines = self.config_id.source_line_ids.sorted(
            lambda source: (source.sequence, source.id)
        )
        availability = {}
        for source in source_lines:
            quantities = self.config_id._get_quantity_map(products, source.warehouse_id)
            draft_out = self.config_id._get_open_draft_quantity(
                products, source.warehouse_id, "out"
            )
            availability[source.id] = {
                product.id: max(
                    0.0,
                    quantities.get(product.id, {}).get("free_qty", 0.0)
                    - draft_out.get(product.id, 0.0),
                )
                for product in products
            }

        allocation_values = []
        for line in lines:
            remaining = line.suggested_qty
            rounding = line.uom_id.rounding
            for source in source_lines:
                available = availability[source.id].get(line.product_id.id, 0.0)
                if float_compare(remaining, 0.0, precision_rounding=rounding) <= 0:
                    break
                if float_compare(available, 0.0, precision_rounding=rounding) <= 0:
                    continue
                if float_compare(available, remaining, precision_rounding=rounding) >= 0:
                    allocated = remaining
                else:
                    allocated = float_round(
                        available,
                        precision_rounding=rounding,
                        rounding_method="DOWN",
                    )
                if float_compare(allocated, 0.0, precision_rounding=rounding) <= 0:
                    continue
                allocation_values.append(
                    {
                        "batch_id": self.id,
                        "line_id": line.id,
                        "source_id": source.id,
                        "warehouse_id": source.warehouse_id.id,
                        "priority": source.sequence,
                        "available_qty": available,
                        "allocated_qty": allocated,
                    }
                )
                remaining -= allocated
                availability[source.id][line.product_id.id] = max(
                    0.0, available - allocated
                )
        if allocation_values:
            self.env["sng.biweekly.replenishment.allocation"].create(
                allocation_values
            )

    def _schedule_for_users(self, record, users, summary, note=""):
        for user in users:
            record.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=summary,
                note=note,
            )

    def action_generate_pickings(self):
        self.ensure_one()
        if self.cancelled:
            raise UserError(_("No puede generar transferencias para un ciclo cancelado."))
        if self.picking_ids:
            return self.action_view_pickings()
        if not self.line_ids:
            self.action_recalculate()

        scheduled_date = fields.Datetime.now() + timedelta(
            days=self.config_id.lead_time_days
        )
        allocations_by_source = defaultdict(
            lambda: self.env["sng.biweekly.replenishment.allocation"]
        )
        for allocation in self.allocation_ids.filtered(
            lambda item: item.allocated_qty > 0
        ):
            allocations_by_source[allocation.source_id] |= allocation

        created_pickings = self.env["stock.picking"]
        for source, allocations in allocations_by_source.items():
            warehouse = source.warehouse_id
            picking_type = warehouse.int_type_id
            if not picking_type:
                raise UserError(
                    _(
                        "El CEDIS %(warehouse)s no tiene un tipo de operación interna.",
                        warehouse=warehouse.display_name,
                    )
                )
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": self.main_warehouse_id.lot_stock_id.id,
                    "scheduled_date": scheduled_date,
                    "origin": self.name,
                    "company_id": self.company_id.id,
                    "sng_replenishment_batch_id": self.id,
                    "sng_replenishment_source_id": source.id,
                }
            )
            created_pickings |= picking
            for allocation in allocations:
                move = self.env["stock.move"].create(
                    {
                        "name": allocation.line_id.product_id.display_name,
                        "product_id": allocation.line_id.product_id.id,
                        "product_uom_qty": allocation.allocated_qty,
                        "product_uom": allocation.line_id.uom_id.id,
                        "picking_id": picking.id,
                        "location_id": warehouse.lot_stock_id.id,
                        "location_dest_id": self.main_warehouse_id.lot_stock_id.id,
                        "company_id": self.company_id.id,
                        "sng_replenishment_line_id": allocation.line_id.id,
                    }
                )
                allocation.write({"picking_id": picking.id, "move_id": move.id})
            self._schedule_for_users(
                picking,
                source.responsible_user_ids,
                _("Preparar reabastecimiento %(batch)s", batch=self.name),
                _(
                    "Transferencia en borrador desde %(warehouse)s hacia %(destination)s.",
                    warehouse=warehouse.display_name,
                    destination=self.main_warehouse_id.display_name,
                ),
            )

        self.generated_at = fields.Datetime.now()
        self._schedule_for_users(
            self,
            self.config_id.planner_user_ids,
            _("Revisar ciclo de reabastecimiento %(batch)s", batch=self.name),
        )
        if any(line.shortage_qty > 0 for line in self.line_ids):
            self._schedule_for_users(
                self,
                self.config_id.planner_user_ids,
                _("Faltantes en reabastecimiento %(batch)s", batch=self.name),
                _("Uno o más SKU no pudieron abastecerse completamente."),
            )
        self.message_post(
            body=_(
                "Se generaron %(pickings)s transferencia(s) en borrador por "
                "%(quantity)s unidades asignadas.",
                pickings=len(created_pickings),
                quantity=self.total_allocated_qty,
            )
        )
        return self.action_view_pickings() if created_pickings else self._get_form_action()

    def action_cancel(self):
        for batch in self:
            open_pickings = batch.picking_ids.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            )
            if open_pickings:
                open_pickings.action_cancel()
            batch.cancelled = True
            batch.message_post(body=_("Ciclo cancelado; se conservará su historial."))
        return True

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        action["domain"] = [("sng_replenishment_batch_id", "=", self.id)]
        action["context"] = {
            "default_sng_replenishment_batch_id": self.id,
            "create": False,
        }
        return action

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            "sng_biweekly_replenishment.action_replenishment_batch_pdf"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        return self.env.ref(
            "sng_biweekly_replenishment.action_replenishment_batch_xlsx"
        ).report_action(self)


class SngBiweeklyReplenishmentLine(models.Model):
    _name = "sng.biweekly.replenishment.line"
    _description = "Línea de Reabastecimiento Bisemanal"
    _order = "product_code, product_id, id"
    _check_company_auto = True

    batch_id = fields.Many2one(
        "sng.biweekly.replenishment.batch",
        string="Ciclo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="batch_id.company_id", store=True)
    config_id = fields.Many2one(related="batch_id.config_id", store=True)
    main_warehouse_id = fields.Many2one(
        related="batch_id.main_warehouse_id",
        store=True,
    )
    run_date = fields.Date(related="batch_id.run_date", store=True)
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    product_code = fields.Char(
        related="product_id.default_code",
        string="Código",
        store=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidad",
        required=True,
        readonly=True,
    )
    demand_qty = fields.Float(
        string="Salidas 14 días",
        digits="Product Unit of Measure",
        readonly=True,
    )
    daily_demand = fields.Float(
        string="Demanda diaria",
        digits="Product Unit of Measure",
        readonly=True,
    )
    coverage_days = fields.Integer(string="Cobertura", readonly=True)
    safety_days = fields.Integer(string="Seguridad", readonly=True)
    lead_time_days = fields.Integer(string="Plazo", readonly=True)
    target_stock = fields.Float(
        string="Stock objetivo",
        digits="Product Unit of Measure",
        readonly=True,
    )
    reorder_point = fields.Float(
        string="Punto de reorden",
        digits="Product Unit of Measure",
        readonly=True,
    )
    free_qty = fields.Float(
        string="Stock libre",
        digits="Product Unit of Measure",
        readonly=True,
    )
    forecast_qty = fields.Float(
        string="Stock previsto",
        digits="Product Unit of Measure",
        readonly=True,
    )
    draft_in_qty = fields.Float(
        string="Entradas borrador previas",
        digits="Product Unit of Measure",
        readonly=True,
    )
    draft_out_qty = fields.Float(
        string="Salidas borrador previas",
        digits="Product Unit of Measure",
        readonly=True,
    )
    projected_qty = fields.Float(
        string="Stock proyectado",
        digits="Product Unit of Measure",
        readonly=True,
    )
    suggested_qty = fields.Float(
        string="Cantidad sugerida",
        digits="Product Unit of Measure",
        readonly=True,
    )
    allocation_ids = fields.One2many(
        "sng.biweekly.replenishment.allocation",
        "line_id",
        string="Asignaciones",
        readonly=True,
    )
    allocated_qty = fields.Float(
        string="Cantidad asignada",
        compute="_compute_allocation_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    shortage_qty = fields.Float(
        string="Cantidad faltante",
        compute="_compute_allocation_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    allocation_summary = fields.Char(
        string="Distribución por CEDIS",
        compute="_compute_allocation_summary",
    )

    _sql_constraints = [
        (
            "batch_product_unique",
            "unique(batch_id, product_id)",
            "El producto solo puede aparecer una vez por ciclo.",
        )
    ]

    @api.depends("allocation_ids.allocated_qty", "suggested_qty")
    def _compute_allocation_totals(self):
        for line in self:
            allocated = sum(line.allocation_ids.mapped("allocated_qty"))
            line.allocated_qty = allocated
            line.shortage_qty = max(0.0, line.suggested_qty - allocated)

    @api.depends(
        "allocation_ids.allocated_qty",
        "allocation_ids.warehouse_id",
        "allocation_ids.picking_id",
    )
    def _compute_allocation_summary(self):
        for line in self:
            parts = []
            for allocation in line.allocation_ids.sorted(
                lambda item: (item.priority, item.id)
            ):
                reference = allocation.picking_id.name or _("Borrador pendiente")
                parts.append(
                    "%s: %s (%s)"
                    % (
                        allocation.warehouse_id.code,
                        allocation.allocated_qty,
                        reference,
                    )
                )
            line.allocation_summary = "; ".join(parts)


class SngBiweeklyReplenishmentAllocation(models.Model):
    _name = "sng.biweekly.replenishment.allocation"
    _description = "Asignación de Reabastecimiento por CEDIS"
    _order = "priority, warehouse_id, id"
    _check_company_auto = True

    batch_id = fields.Many2one(
        "sng.biweekly.replenishment.batch",
        string="Ciclo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    line_id = fields.Many2one(
        "sng.biweekly.replenishment.line",
        string="SKU",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="batch_id.company_id", store=True)
    source_id = fields.Many2one(
        "sng.biweekly.replenishment.source",
        string="Configuración CEDIS",
        required=True,
        ondelete="restrict",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="CEDIS",
        required=True,
        check_company=True,
        index=True,
    )
    product_id = fields.Many2one(related="line_id.product_id", store=True)
    uom_id = fields.Many2one(related="line_id.uom_id", store=True)
    priority = fields.Integer(readonly=True)
    available_qty = fields.Float(
        string="Disponible al calcular",
        digits="Product Unit of Measure",
        readonly=True,
    )
    allocated_qty = fields.Float(
        string="Cantidad asignada",
        digits="Product Unit of Measure",
        required=True,
        readonly=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Transferencia",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    move_id = fields.Many2one(
        "stock.move",
        string="Movimiento",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    _sql_constraints = [
        (
            "line_source_unique",
            "unique(line_id, source_id)",
            "Solo puede existir una asignación por SKU y CEDIS.",
        ),
        (
            "allocated_qty_positive",
            "check(allocated_qty > 0)",
            "La cantidad asignada debe ser mayor que cero.",
        ),
    ]
