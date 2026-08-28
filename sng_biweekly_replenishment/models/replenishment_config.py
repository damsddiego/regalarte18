# -*- coding: utf-8 -*-

import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class SngBiweeklyReplenishmentConfig(models.Model):
    _name = "sng.biweekly.replenishment.config"
    _description = "Configuración de Reabastecimiento Bisemanal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name, id"
    _check_company_auto = True

    name = fields.Char(string="Nombre", required=True, tracking=True)
    active = fields.Boolean(default=True)
    automation_active = fields.Boolean(
        string="Automatización activa",
        default=False,
        tracking=True,
        help="Si está activa, el cron generará el ciclo al alcanzar la próxima fecha.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    warehouse_group_id = fields.Many2one(
        "sng.warehouse.group",
        string="Grupo de almacenes",
        required=True,
        tracking=True,
    )
    available_warehouse_ids = fields.Many2many(
        related="warehouse_group_id.warehouse_ids",
        string="Almacenes disponibles",
        readonly=True,
    )
    main_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Bodega Principal",
        required=True,
        check_company=True,
        tracking=True,
    )
    source_line_ids = fields.One2many(
        "sng.biweekly.replenishment.source",
        "config_id",
        string="CEDIS de origen",
        copy=True,
    )
    demand_picking_type_ids = fields.Many2many(
        "stock.picking.type",
        "sng_biweekly_replenishment_config_picking_type_rel",
        "config_id",
        "picking_type_id",
        string="Operaciones que representan salidas",
        check_company=True,
        help="Solo movimientos terminados de estos tipos forman la demanda histórica.",
    )
    product_ids = fields.Many2many(
        "product.product",
        "sng_biweekly_replenishment_config_product_rel",
        "config_id",
        "product_id",
        string="Productos incluidos",
        domain=[("is_storable", "=", True)],
        help="Vacío incluye todos los productos almacenables activos.",
    )
    category_ids = fields.Many2many(
        "product.category",
        "sng_biweekly_replenishment_config_category_rel",
        "config_id",
        "category_id",
        string="Categorías incluidas",
        help="Vacío no restringe por categoría.",
    )
    planner_user_ids = fields.Many2many(
        "res.users",
        "sng_biweekly_replenishment_config_user_rel",
        "config_id",
        "user_id",
        string="Planificadores responsables",
        domain="[('company_ids', 'in', company_id)]",
    )
    demand_window_days = fields.Integer(
        string="Ventana histórica (días)",
        default=14,
        required=True,
        readonly=True,
    )
    coverage_days = fields.Integer(
        string="Días de cobertura",
        default=14,
        required=True,
        tracking=True,
    )
    safety_days = fields.Integer(
        string="Días de seguridad",
        default=2,
        required=True,
        tracking=True,
    )
    lead_time_days = fields.Integer(
        string="Plazo interno (días)",
        default=1,
        required=True,
        tracking=True,
    )
    cycle_interval_days = fields.Integer(
        string="Periodicidad (días)",
        default=14,
        required=True,
        tracking=True,
    )
    next_run_date = fields.Date(
        string="Próximo ciclo",
        default=lambda self: fields.Date.context_today(self) + timedelta(days=14),
        required=True,
        tracking=True,
    )
    last_alert_check_date = fields.Date(
        string="Última revisión de alertas",
        readonly=True,
        copy=False,
    )
    batch_ids = fields.One2many(
        "sng.biweekly.replenishment.batch",
        "config_id",
        string="Ciclos",
        readonly=True,
    )
    batch_count = fields.Integer(compute="_compute_batch_count")

    _sql_constraints = [
        (
            "main_warehouse_company_unique",
            "unique(main_warehouse_id, company_id)",
            "Solo puede existir una configuración por Bodega Principal y compañía.",
        ),
        (
            "coverage_days_positive",
            "check(coverage_days > 0)",
            "Los días de cobertura deben ser mayores que cero.",
        ),
        (
            "safety_days_nonnegative",
            "check(safety_days >= 0)",
            "Los días de seguridad no pueden ser negativos.",
        ),
        (
            "lead_time_days_nonnegative",
            "check(lead_time_days >= 0)",
            "El plazo interno no puede ser negativo.",
        ),
        (
            "cycle_interval_days_positive",
            "check(cycle_interval_days > 0)",
            "La periodicidad debe ser mayor que cero.",
        ),
    ]

    @api.depends("batch_ids")
    def _compute_batch_count(self):
        grouped = self.env["sng.biweekly.replenishment.batch"]._read_group(
            [("config_id", "in", self.ids)],
            ["config_id"],
            ["__count"],
        )
        counts = {config.id: count for config, count in grouped}
        for config in self:
            config.batch_count = counts.get(config.id, 0)

    @api.onchange("main_warehouse_id")
    def _onchange_main_warehouse_id(self):
        for config in self:
            if not config.main_warehouse_id:
                continue
            config.company_id = config.main_warehouse_id.company_id
            config.demand_picking_type_ids = config._get_default_demand_picking_types()

    @api.constrains(
        "company_id",
        "warehouse_group_id",
        "main_warehouse_id",
        "source_line_ids",
        "demand_picking_type_ids",
    )
    def _check_warehouse_configuration(self):
        for config in self:
            group_warehouses = config.warehouse_group_id.warehouse_ids
            if config.main_warehouse_id not in group_warehouses:
                raise ValidationError(
                    _("La Bodega Principal debe pertenecer al grupo de almacenes seleccionado.")
                )
            if not config.source_line_ids:
                raise ValidationError(_("Debe configurar al menos un CEDIS de origen."))
            sources = config.source_line_ids.mapped("warehouse_id")
            if len(sources) != len(config.source_line_ids):
                raise ValidationError(_("No puede repetir un CEDIS de origen."))
            if config.main_warehouse_id in sources:
                raise ValidationError(_("La Bodega Principal no puede ser un CEDIS de origen."))
            if sources - group_warehouses:
                raise ValidationError(
                    _("Todos los CEDIS deben pertenecer al grupo de almacenes seleccionado.")
                )
            if any(warehouse.company_id != config.company_id for warehouse in sources):
                raise ValidationError(
                    _("Todos los almacenes deben pertenecer a la misma compañía.")
                )
            if any(
                picking_type.company_id
                and picking_type.company_id != config.company_id
                for picking_type in config.demand_picking_type_ids
            ):
                raise ValidationError(
                    _("Los tipos de operación deben pertenecer a la compañía configurada.")
                )

    def _get_default_demand_picking_types(self):
        self.ensure_one()
        if not self.main_warehouse_id:
            return self.env["stock.picking.type"]
        return self.env["stock.picking.type"].search(
            [
                ("warehouse_id", "=", self.main_warehouse_id.id),
                "|",
                ("code", "=", "outgoing"),
                ("sequence_code", "in", ["RELL", "CONS", "REGOUT"]),
            ]
        )

    def _get_product_domain(self):
        self.ensure_one()
        domain = [
            ("active", "=", True),
            ("is_storable", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.company_id.id),
        ]
        if self.product_ids:
            domain.append(("id", "in", self.product_ids.ids))
        if self.category_ids:
            domain.append(("categ_id", "child_of", self.category_ids.ids))
        return domain

    def _get_demand_by_product(self, period_start, period_end):
        """Return gross physical demand normalized to each product's base UoM."""
        self.ensure_one()
        if not self.demand_picking_type_ids:
            raise UserError(
                _("Configure al menos un tipo de operación que represente salidas.")
            )
        product_domain = self._get_product_domain()
        products = self.env["product.product"].search(product_domain)
        if not products:
            return {}

        physical_internal_codes = ["CONS", "REGOUT"]
        domain = [
            ("state", "=", "done"),
            ("date", ">=", period_start),
            ("date", "<", period_end),
            ("product_id", "in", products.ids),
            ("picking_type_id", "in", self.demand_picking_type_ids.ids),
            ("location_id.warehouse_id", "=", self.main_warehouse_id.id),
            ("location_dest_id.usage", "!=", "inventory"),
            ("is_inventory", "=", False),
            "|",
            "|",
            ("location_dest_id.warehouse_id", "=", False),
            ("location_dest_id.warehouse_id", "!=", self.main_warehouse_id.id),
            ("picking_type_id.sequence_code", "in", physical_internal_codes),
        ]
        grouped = self.env["stock.move"]._read_group(
            domain,
            ["product_id", "product_uom"],
            ["quantity:sum"],
        )
        demand = defaultdict(float)
        for product, uom, quantity in grouped:
            demand[product.id] += uom._compute_quantity(
                quantity,
                product.uom_id,
                round=False,
            )
        return dict(demand)

    def _get_quantity_map(self, products, warehouse):
        self.ensure_one()
        if not products:
            return {}
        products.invalidate_recordset(["free_qty", "virtual_available"])
        rows = products.with_context(warehouse_id=warehouse.id).read(
            ["free_qty", "virtual_available"]
        )
        return {
            row["id"]: {
                "free_qty": row["free_qty"],
                "virtual_available": row["virtual_available"],
            }
            for row in rows
        }

    def _get_open_draft_quantity(self, products, warehouse, direction):
        """Quantities in our draft pickings; core forecasts intentionally ignore drafts."""
        self.ensure_one()
        if not products:
            return {}
        if direction == "out":
            location_domain = [("location_id.warehouse_id", "=", warehouse.id)]
        else:
            location_domain = [("location_dest_id.warehouse_id", "=", warehouse.id)]
        domain = [
            ("state", "=", "draft"),
            ("product_id", "in", products.ids),
            ("sng_replenishment_line_id", "!=", False),
        ] + location_domain
        grouped = self.env["stock.move"]._read_group(
            domain,
            ["product_id"],
            ["product_qty:sum"],
        )
        return {product.id: quantity for product, quantity in grouped}

    def _prepare_cycle(self, run_date=None):
        self.ensure_one()
        run_date = fields.Date.to_date(run_date or fields.Date.context_today(self))
        batch = self.env["sng.biweekly.replenishment.batch"].search(
            [("config_id", "=", self.id), ("run_date", "=", run_date)],
            limit=1,
        )
        if batch:
            return batch
        period_end = fields.Datetime.now()
        period_start = period_end - timedelta(days=self.demand_window_days)
        return self.env["sng.biweekly.replenishment.batch"].create(
            {
                "config_id": self.id,
                "run_date": run_date,
                "period_start": period_start,
                "period_end": period_end,
            }
        )

    def action_preview_cycle(self):
        self.ensure_one()
        batch = self._prepare_cycle()
        if not batch.picking_ids:
            batch.action_recalculate()
        return batch._get_form_action()

    def action_run_now(self):
        self.ensure_one()
        batch = self._prepare_cycle()
        if not batch.picking_ids:
            batch.action_recalculate()
            batch.action_generate_pickings()
        return batch._get_form_action()

    def action_view_batches(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sng_biweekly_replenishment.action_replenishment_batch"
        )
        action["domain"] = [("config_id", "=", self.id)]
        action["context"] = {"default_config_id": self.id}
        return action

    @api.model
    def _cron_generate_due_cycles(self):
        today = fields.Date.context_today(self)
        configs = self.search(
            [
                ("active", "=", True),
                ("automation_active", "=", True),
                ("next_run_date", "<=", today),
            ],
            order="next_run_date, id",
        )
        for config in configs:
            try:
                with self.env.cr.savepoint():
                    self.env.cr.execute(
                        "SELECT id FROM sng_biweekly_replenishment_config "
                        "WHERE id = %s FOR UPDATE SKIP LOCKED",
                        [config.id],
                    )
                    if not self.env.cr.fetchone():
                        continue
                    config.invalidate_recordset(["next_run_date", "automation_active"])
                    if not config.automation_active or config.next_run_date > today:
                        continue
                    batch = config._prepare_cycle(run_date=today)
                    if not batch.picking_ids:
                        batch.action_recalculate()
                        batch.action_generate_pickings()
                    next_date = config.next_run_date
                    while next_date <= today:
                        next_date += timedelta(days=config.cycle_interval_days)
                    config.next_run_date = next_date
            except Exception:
                _logger.exception(
                    "No se pudo generar el ciclo bisemanal para la configuración %s",
                    config.display_name,
                )

    @api.model
    def _cron_check_reorder_alerts(self):
        today = fields.Date.context_today(self)
        configs = self.search(
            [
                ("active", "=", True),
                ("automation_active", "=", True),
                "|",
                ("last_alert_check_date", "=", False),
                ("last_alert_check_date", "<", today),
            ]
        )
        for config in configs:
            try:
                with self.env.cr.savepoint():
                    config._check_reorder_alerts()
                    config.last_alert_check_date = today
            except Exception:
                _logger.exception(
                    "No se pudieron revisar alertas de reorden para %s",
                    config.display_name,
                )


class SngBiweeklyReplenishmentSource(models.Model):
    _name = "sng.biweekly.replenishment.source"
    _description = "CEDIS de Reabastecimiento"
    _order = "sequence, id"
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    config_id = fields.Many2one(
        "sng.biweekly.replenishment.config",
        string="Configuración",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True)
    available_warehouse_ids = fields.Many2many(
        related="config_id.warehouse_group_id.warehouse_ids",
        string="Almacenes disponibles",
        readonly=True,
    )
    main_warehouse_id = fields.Many2one(
        related="config_id.main_warehouse_id",
        string="Bodega Principal",
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="CEDIS",
        required=True,
        check_company=True,
    )
    responsible_user_ids = fields.Many2many(
        "res.users",
        "sng_biweekly_replenishment_source_user_rel",
        "source_id",
        "user_id",
        string="Responsables",
        domain="[('company_ids', 'in', company_id)]",
    )

    _sql_constraints = [
        (
            "config_warehouse_unique",
            "unique(config_id, warehouse_id)",
            "No puede repetir un CEDIS en la misma configuración.",
        )
    ]

    @api.constrains("warehouse_id", "config_id")
    def _check_source_warehouse(self):
        for source in self:
            if not source.config_id or not source.warehouse_id:
                continue
            if source.warehouse_id == source.config_id.main_warehouse_id:
                raise ValidationError(_("El CEDIS no puede ser la Bodega Principal."))
            if source.warehouse_id.company_id != source.config_id.company_id:
                raise ValidationError(_("El CEDIS debe pertenecer a la misma compañía."))
