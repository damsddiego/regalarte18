# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CommissionPlan(models.Model):
    _name = "sng.commission.plan"
    _description = "Plan de comisiones"
    _order = "date_start desc, id desc"

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda de liquidación",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    date_start = fields.Date(string="Fecha inicio", required=True)
    date_end = fields.Date(
        string="Fecha fin",
        help="Dejar vacío para que el plan siga vigente hasta que se active un plan nuevo.",
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("active", "Activo"),
            ("archived", "Archivado"),
        ],
        string="Estado",
        default="draft",
        required=True,
    )
    active = fields.Boolean(default=True)
    aging_rule_ids = fields.One2many(
        "sng.commission.aging.rule",
        "plan_id",
        string="Buckets de antigüedad",
        copy=True,
    )
    performance_rule_ids = fields.One2many(
        "sng.commission.performance.rule",
        "plan_id",
        string="Tabla de cumplimiento",
        copy=True,
    )
    settlement_ids = fields.One2many(
        "sng.commission.settlement",
        "plan_id",
        string="Liquidaciones",
    )

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_end < record.date_start:
                raise ValidationError(_("La fecha final no puede ser menor que la fecha inicial."))

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for record in self:
            record.currency_id = record.company_id.currency_id

    @api.constrains("state", "active", "date_start", "date_end", "company_id")
    def _check_active_overlaps(self):
        for record in self.filtered(lambda plan: plan.active and plan.state == "active"):
            domain = [
                ("id", "!=", record.id),
                ("company_id", "=", record.company_id.id),
                ("active", "=", True),
                ("state", "=", "active"),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", record.date_start),
            ]
            if record.date_end:
                domain.append(("date_start", "<=", record.date_end))
            if self.search_count(domain):
                raise ValidationError(
                    _("No se permiten planes activos con vigencias traslapadas para la misma compañía.")
                )

    @api.constrains("state", "aging_rule_ids", "performance_rule_ids")
    def _check_required_active_configuration(self):
        self.filtered(lambda plan: plan.active and plan.state == "active")._check_required_configuration()

    def _check_required_configuration(self):
        for record in self:
            not_due_rules = record.aging_rule_ids.filtered(lambda rule: rule.bucket_type == "not_due")
            overdue_rules = record.aging_rule_ids.filtered(lambda rule: rule.bucket_type == "overdue")
            if not not_due_rules:
                raise ValidationError(
                    _("El plan %(plan)s debe tener un bucket de antigüedad de tipo 'No vencido'.",
                      plan=record.display_name)
                )
            if not overdue_rules:
                raise ValidationError(
                    _("El plan %(plan)s debe tener al menos un bucket de antigüedad vencida.",
                      plan=record.display_name)
                )
            if not record.performance_rule_ids:
                raise ValidationError(
                    _("El plan %(plan)s debe tener al menos una regla de cumplimiento.",
                      plan=record.display_name)
                )

    def action_activate(self):
        self._check_required_configuration()
        self._close_previous_active_plans()
        self.write({"state": "active"})

    def _close_previous_active_plans(self):
        for record in self:
            if not record.date_start:
                continue
            previous_end = record.date_start - timedelta(days=1)
            previous_plans = self.search(
                [
                    ("id", "!=", record.id),
                    ("company_id", "=", record.company_id.id),
                    ("active", "=", True),
                    ("state", "=", "active"),
                    ("date_start", "<", record.date_start),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", record.date_start),
                ]
            )
            previous_plans.write({"date_end": previous_end})

    def action_archive(self):
        self.write({"state": "archived"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    def _get_aging_rule(self, days_overdue):
        self.ensure_one()
        if days_overdue <= 0:
            return self.aging_rule_ids.filtered(lambda rule: rule.bucket_type == "not_due")[:1]
        return self.aging_rule_ids.filtered(
            lambda rule: rule.bucket_type == "overdue"
            and rule.days_from <= days_overdue <= rule.days_to
        )[:1]

    def _get_performance_rule(self, achievement_percentage):
        self.ensure_one()
        return self.performance_rule_ids.filtered(
            lambda rule: rule.percentage_from <= achievement_percentage <= rule.percentage_to
        )[:1]


class CommissionAgingRule(models.Model):
    _name = "sng.commission.aging.rule"
    _description = "Regla de antigüedad"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one("sng.commission.plan", string="Plan", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="plan_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="plan_id.currency_id", store=True, readonly=True)
    name = fields.Char(string="Etiqueta", required=True)
    bucket_type = fields.Selection(
        [
            ("not_due", "No vencido"),
            ("overdue", "Vencido"),
        ],
        string="Tipo",
        required=True,
        default="overdue",
    )
    days_from = fields.Integer(string="Desde días")
    days_to = fields.Integer(string="Hasta días")
    commission_percentage = fields.Float(string="% comisión base", required=True)

    @api.constrains("bucket_type", "days_from", "days_to")
    def _check_days(self):
        for record in self:
            if record.bucket_type == "not_due":
                continue
            if record.days_from < 1 or record.days_to < 1:
                raise ValidationError(_("Los rangos de antigüedad vencida deben ser mayores que cero."))
            if record.days_to < record.days_from:
                raise ValidationError(_("El rango final no puede ser menor que el inicial."))

    @api.constrains("plan_id", "bucket_type", "days_from", "days_to")
    def _check_overlap(self):
        for record in self:
            siblings = record.plan_id.aging_rule_ids - record
            if record.bucket_type == "not_due":
                if siblings.filtered(lambda rule: rule.bucket_type == "not_due"):
                    raise ValidationError(_("Solo puede existir un bucket de tipo 'No vencido' por plan."))
                continue
            for sibling in siblings.filtered(lambda rule: rule.bucket_type == "overdue"):
                if sibling.days_from <= record.days_to and sibling.days_to >= record.days_from:
                    raise ValidationError(_("Los buckets de antigüedad vencida no pueden traslaparse."))

class CommissionPerformanceRule(models.Model):
    _name = "sng.commission.performance.rule"
    _description = "Regla de cumplimiento"
    _order = "sequence, percentage_from desc, id"

    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one("sng.commission.plan", string="Plan", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="plan_id.company_id", store=True, readonly=True)
    name = fields.Char(string="Etiqueta")
    percentage_from = fields.Float(string="% desde", required=True)
    percentage_to = fields.Float(string="% hasta", required=True)
    payout_factor = fields.Float(
        string="Factor de pago (%)",
        required=True,
        default=100.0,
        help="Porcentaje del pago sobre la comisión base. Ejemplo: 100 = pago completo, 110 = 10% adicional, 50 = 50% de la comisión.",
    )

    @api.constrains("payout_factor")
    def _check_payout_factor(self):
        for record in self:
            if record.payout_factor < 0:
                raise ValidationError(_("El factor de pago no puede ser negativo."))

    @api.constrains("percentage_from", "percentage_to")
    def _check_percentage_range(self):
        for record in self:
            if record.percentage_to < record.percentage_from:
                raise ValidationError(_("El porcentaje final no puede ser menor que el inicial."))

    @api.constrains("plan_id", "percentage_from", "percentage_to")
    def _check_overlap(self):
        for record in self:
            siblings = record.plan_id.performance_rule_ids - record
            for sibling in siblings:
                if sibling.percentage_from <= record.percentage_to and sibling.percentage_to >= record.percentage_from:
                    raise ValidationError(_("Las reglas de cumplimiento no pueden traslaparse."))
