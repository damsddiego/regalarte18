# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SngCommercialPlanHistory(models.Model):
    _name = 'sng.commercial.plan.history'
    _description = 'Venta Historica Plan Comercial'
    _order = 'date_from desc, amount desc, id asc'

    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Moneda',
        store=True,
        readonly=True,
    )
    date_from = fields.Date(string='Periodo Desde', required=True, index=True)
    date_to = fields.Date(string='Periodo Hasta', required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        index=True,
        ondelete='restrict',
        context={'active_test': False},
    )
    source_code = fields.Char(string='Codigo Origen', index=True)
    source_name = fields.Char(string='Cliente Origen')
    amount = fields.Monetary(string='Venta Neta')
    source_file = fields.Char(string='Archivo Origen')
    match_method = fields.Selection(
        selection=[
            ('code', 'Codigo'),
            ('name', 'Nombre'),
            ('history', 'Asignacion previa'),
            ('manual', 'Manual'),
            ('none', 'Sin asignar'),
        ],
        string='Asignado por',
        default='none',
        required=True,
        index=True,
    )
    note = fields.Char(string='Observacion')

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._normalize_partner_vals(vals) for vals in vals_list])

    def write(self, vals):
        if 'partner_id' in vals:
            vals = self._normalize_partner_vals(vals)
            if 'match_method' not in vals:
                vals['match_method'] = 'manual' if vals.get('partner_id') else 'none'
        return super().write(vals)

    @api.model
    def _normalize_partner_vals(self, vals):
        values = dict(vals)
        if values.get('partner_id'):
            partner = self.env['res.partner'].browse(values['partner_id'])
            values['partner_id'] = partner.commercial_partner_id.id
        return values

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_period(self):
        periods = set()
        for record in self:
            if record.date_from > record.date_to:
                raise ValidationError(_('La fecha inicial del historico no puede superar la fecha final.'))
            start_date = record.company_id.sng_plan_odoo_start_date
            if start_date and record.date_to >= start_date:
                raise ValidationError(_(
                    'El historico debe terminar antes del inicio de ventas en Odoo (%s). '
                    'Desde esa fecha la venta se toma de las facturas.'
                ) % fields.Date.to_string(start_date))
            periods.add((record.company_id.id, record.date_from, record.date_to))

        for company_id, date_from, date_to in periods:
            overlapping = self.search([
                ('company_id', '=', company_id),
                ('date_from', '<=', date_to),
                ('date_to', '>=', date_from),
                '|',
                ('date_from', '!=', date_from),
                ('date_to', '!=', date_to),
            ], limit=1)
            if overlapping:
                raise ValidationError(_(
                    'El periodo %(new_from)s - %(new_to)s se traslapa con el historico '
                    '%(old_from)s - %(old_to)s. Elimine uno de los dos para no duplicar ventas.'
                ) % {
                    'new_from': fields.Date.to_string(date_from),
                    'new_to': fields.Date.to_string(date_to),
                    'old_from': fields.Date.to_string(overlapping.date_from),
                    'old_to': fields.Date.to_string(overlapping.date_to),
                })
