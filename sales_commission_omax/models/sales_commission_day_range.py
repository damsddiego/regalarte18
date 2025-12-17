# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalesCommissionDayRange(models.Model):
    _name = 'sales.commission.day.range'
    _description = 'Sales Commission Day Range'
    _order = 'commission_id, min_days, max_days'

    commission_id = fields.Many2one(
        'sales.commission',
        string='Commission',
        required=True,
        ondelete='cascade'
    )
    name = fields.Char(string='Range', compute='_compute_name', store=True)
    min_days = fields.Integer(string='Min Days', required=True, help='Inclusive lower bound of the range.')
    max_days = fields.Integer(string='Max Days', help='Inclusive upper bound of the range. Leave empty for no upper bound.')
    commission_percentage = fields.Float(string='Commission %', required=True)

    @api.depends('min_days', 'max_days')
    def _compute_name(self):
        for record in self:
            if record.max_days or record.max_days == 0:
                record.name = _("%(min)s-%(max)s days", min=record.min_days, max=record.max_days)
            else:
                record.name = _("%(min)s+ days", min=record.min_days)

    def matches(self, days):
        self.ensure_one()
        upper_bound = self.max_days if (self.max_days or self.max_days == 0) else None
        if days < self.min_days:
            return False
        if upper_bound is not None and days > upper_bound:
            return False
        return True

    @api.constrains('min_days', 'max_days', 'commission_percentage')
    def _check_values(self):
        for record in self:
            if record.min_days < 0:
                raise ValidationError(_('Min days must be greater than or equal to 0.'))
            if (record.max_days or record.max_days == 0) and record.max_days < record.min_days:
                raise ValidationError(_('Max days must be greater than or equal to min days.'))
            if record.commission_percentage <= 0:
                raise ValidationError(_('Commission percentage must be greater than 0.'))

    @api.constrains('min_days', 'max_days', 'commission_id')
    def _check_overlapping_ranges(self):
        for record in self:
            if not record.commission_id:
                continue
            ranges = record.commission_id.day_range_ids - record + record
            sorted_ranges = ranges.sorted(lambda r: (r.min_days, r.max_days if (r.max_days or r.max_days == 0) else float('inf')))
            last_upper = -1
            for range_item in sorted_ranges:
                current_upper = range_item.max_days if (range_item.max_days or range_item.max_days == 0) else float('inf')
                if range_item.min_days <= last_upper:
                    raise ValidationError(_('Day ranges cannot overlap for the same commission.'))
                last_upper = current_upper