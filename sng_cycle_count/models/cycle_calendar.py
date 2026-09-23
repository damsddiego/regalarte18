# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    cycle_supervisor_id = fields.Many2one(
        "res.users", string="Responsable de conteos cíclicos",
        domain="[('share', '=', False)]",
    )
    cycle_calendar_id = fields.Many2one(
        "resource.calendar", string="Calendario de conteos y feriados",
        domain="[('company_id', 'in', [False, company_id])]",
        help="Los días no laborables globales de este calendario excluyen feriados del plazo.",
    )
    cycle_lock_version = fields.Integer(default=0, copy=False, readonly=True)

    @api.constrains("cycle_supervisor_id", "cycle_calendar_id", "company_id")
    def _check_cycle_configuration(self):
        for warehouse in self:
            user = warehouse.cycle_supervisor_id
            if user and (not user.active or warehouse.company_id not in user.company_ids
                         or not user.has_group("sng_cycle_count.group_cycle_count_supervisor")):
                raise ValidationError(_("El responsable debe ser una Jefatura activa de esta compañía."))
            if warehouse.cycle_calendar_id.company_id not in (self.env["res.company"], warehouse.company_id):
                raise ValidationError(_("El calendario debe pertenecer a la compañía de la bodega."))

    def _cycle_deadlines(self, registered_at):
        """Two subsequent working dates; never a duration of 48 working hours."""
        self.ensure_one()
        tz = pytz.timezone("America/Costa_Rica")
        registered_at = fields.Datetime.to_datetime(registered_at)
        day = pytz.utc.localize(registered_at).astimezone(tz).date()
        calendar = self.cycle_calendar_id or self.company_id.resource_calendar_id
        leaves = self.env["resource.calendar.leaves"].sudo().search([
            ("resource_id", "=", False),
            ("company_id", "in", [False, self.company_id.id]),
            ("calendar_id", "in", [False, calendar.id]),
            ("date_to", ">=", registered_at),
        ])
        remaining = 2
        while remaining:
            day += timedelta(days=1)
            start = tz.localize(datetime.combine(day, time(7, 30))).astimezone(pytz.utc).replace(tzinfo=None)
            end = tz.localize(datetime.combine(day, time(17))).astimezone(pytz.utc).replace(tzinfo=None)
            holiday = any(leave.date_from < end and leave.date_to > start for leave in leaves)
            if day.weekday() < 5 and not holiday:
                remaining -= 1
        return start, end
