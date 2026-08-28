# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare, float_round


class SngBiweeklyReplenishmentAlert(models.Model):
    _name = "sng.biweekly.replenishment.alert"
    _description = "Alerta Dinámica de Punto de Reorden"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "state, last_checked_at desc, id desc"
    _check_company_auto = True

    config_id = fields.Many2one(
        "sng.biweekly.replenishment.config",
        string="Configuración",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True)
    main_warehouse_id = fields.Many2one(
        related="config_id.main_warehouse_id",
        store=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    product_code = fields.Char(related="product_id.default_code", store=True)
    uom_id = fields.Many2one(related="product_id.uom_id", store=True)
    state = fields.Selection(
        [("open", "Abierta"), ("recovered", "Recuperada")],
        string="Estado",
        required=True,
        default="open",
        tracking=True,
        index=True,
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
    first_detected_at = fields.Datetime(readonly=True)
    last_opened_at = fields.Datetime(readonly=True)
    last_checked_at = fields.Datetime(readonly=True)
    recovered_at = fields.Datetime(readonly=True)
    open_count = fields.Integer(string="Episodios", default=1, readonly=True)

    _sql_constraints = [
        (
            "config_product_unique",
            "unique(config_id, product_id)",
            "Solo puede existir una alerta vigente por configuración y producto.",
        )
    ]

    @api.depends("product_id", "config_id")
    def _compute_display_name(self):
        for alert in self:
            alert.display_name = "%s - %s" % (
                alert.product_id.display_name,
                alert.config_id.display_name,
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


class SngBiweeklyReplenishmentConfigAlert(models.Model):
    _inherit = "sng.biweekly.replenishment.config"

    alert_ids = fields.One2many(
        "sng.biweekly.replenishment.alert",
        "config_id",
        string="Alertas",
        readonly=True,
    )
    open_alert_count = fields.Integer(compute="_compute_open_alert_count")

    def _compute_open_alert_count(self):
        grouped = self.env["sng.biweekly.replenishment.alert"]._read_group(
            [("config_id", "in", self.ids), ("state", "=", "open")],
            ["config_id"],
            ["__count"],
        )
        counts = {config.id: count for config, count in grouped}
        for config in self:
            config.open_alert_count = counts.get(config.id, 0)

    def _schedule_alert_activities(self, alert):
        for user in self.planner_user_ids:
            alert.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_(
                    "Reorden requerido: %(product)s",
                    product=alert.product_id.display_name,
                ),
                note=_(
                    "Stock libre %(free)s; punto dinámico de reorden %(point)s.",
                    free=alert.free_qty,
                    point=alert.reorder_point,
                ),
            )

    def _check_reorder_alerts(self):
        self.ensure_one()
        now = fields.Datetime.now()
        period_start = now - timedelta(days=self.demand_window_days)
        demand_map = self._get_demand_by_product(period_start, now)
        existing_alerts = self.env["sng.biweekly.replenishment.alert"].search(
            [("config_id", "=", self.id)]
        )
        product_ids = set(demand_map) | set(existing_alerts.product_id.ids)
        products = self.env["product.product"].browse(product_ids).exists()
        quantities = self._get_quantity_map(products, self.main_warehouse_id)
        alert_by_product = {alert.product_id.id: alert for alert in existing_alerts}

        for product in products:
            demand_qty = demand_map.get(product.id, 0.0)
            daily_demand = demand_qty / self.demand_window_days
            reorder_point = float_round(
                daily_demand * (self.lead_time_days + self.safety_days),
                precision_rounding=product.uom_id.rounding,
                rounding_method="UP",
            )
            free_qty = quantities.get(product.id, {}).get("free_qty", 0.0)
            below_reorder = (
                reorder_point > 0
                and float_compare(
                    free_qty,
                    reorder_point,
                    precision_rounding=product.uom_id.rounding,
                )
                < 0
            )
            alert = alert_by_product.get(product.id)
            values = {
                "demand_qty": demand_qty,
                "daily_demand": daily_demand,
                "reorder_point": reorder_point,
                "free_qty": free_qty,
                "last_checked_at": now,
            }
            if below_reorder:
                if not alert:
                    alert = self.env["sng.biweekly.replenishment.alert"].create(
                        {
                            **values,
                            "config_id": self.id,
                            "product_id": product.id,
                            "state": "open",
                            "first_detected_at": now,
                            "last_opened_at": now,
                            "open_count": 1,
                        }
                    )
                    alert.message_post(
                        body=_(
                            "Stock libre %(free)s por debajo del punto de reorden %(point)s.",
                            free=free_qty,
                            point=reorder_point,
                        )
                    )
                    self._schedule_alert_activities(alert)
                elif alert.state == "recovered":
                    alert.write(
                        {
                            **values,
                            "state": "open",
                            "last_opened_at": now,
                            "recovered_at": False,
                            "open_count": alert.open_count + 1,
                        }
                    )
                    alert.message_post(body=_("La escasez volvió a presentarse."))
                    self._schedule_alert_activities(alert)
                else:
                    alert.write(values)
            elif alert:
                values.update({"state": "recovered", "recovered_at": now})
                was_open = alert.state == "open"
                alert.write(values)
                if was_open:
                    alert.activity_ids.filtered("active").action_feedback(
                        feedback=_("Stock recuperado automáticamente.")
                    )
                    alert.message_post(
                        body=_(
                            "Stock recuperado: %(free)s unidades libres; punto de reorden %(point)s.",
                            free=free_qty,
                            point=reorder_point,
                        )
                    )
        return True

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sng_biweekly_replenishment.action_replenishment_alert"
        )
        action["domain"] = [("config_id", "=", self.id)]
        action["context"] = {"search_default_open": 1}
        return action

