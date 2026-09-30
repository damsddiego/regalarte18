# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SngRouteRotation(models.Model):
    """Orden en que un asesor recorre sus rutas, una posición por semana."""
    _name = 'sng.route.rotation'
    _description = 'Rotación de rutas por asesor'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(related='salesperson_id.name', store=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, index=True,
        default=lambda self: self.env.company)
    salesperson_id = fields.Many2one(
        'res.partner', string='Asesor', required=True,
        domain="[('is_salesperson', '=', True)]")
    slot_ids = fields.One2many(
        'sng.route.rotation.slot', 'rotation_id', string='Semanas del ciclo',
        copy=True)
    start_slot_id = fields.Many2one(
        'sng.route.rotation.slot', string='Iniciar en',
        domain="[('rotation_id', '=', id)]",
        help='Semana del ciclo con la que arranca el primer cronograma. '
             'Después el cronograma continúa donde quedó el anterior.')
    cycle_weeks = fields.Integer(
        string='Semanas del ciclo', compute='_compute_cycle_weeks')

    _sql_constraints = [
        ('salesperson_company_uniq', 'unique(salesperson_id, company_id)',
         'El asesor ya tiene una rotación en esta compañía.'),
    ]

    @api.depends('slot_ids')
    def _compute_cycle_weeks(self):
        for rot in self:
            rot.cycle_weeks = len(rot.slot_ids)

    @api.constrains('slot_ids')
    def _check_slots(self):
        for rot in self:
            if any(not slot.route_ids for slot in rot.slot_ids):
                raise ValidationError(
                    _('Cada semana del ciclo debe tener al menos una ruta.'))

    def _ordered_slots(self):
        self.ensure_one()
        return self.slot_ids.sorted(lambda s: (s.sequence, s.id))

    def _first_slot(self):
        self.ensure_one()
        return self.start_slot_id or self._ordered_slots()[:1]

    def _slot_after(self, slot):
        """Siguiente posición del ciclo (vuelve al inicio al terminar)."""
        self.ensure_one()
        slots = self._ordered_slots()
        if not slots:
            return slots
        if slot not in slots:
            return slots[0]
        return slots[(list(slots).index(slot) + 1) % len(slots)]

    def _next_slot_for(self, date_from, exclude_schedule=None):
        """Posición con la que sigue la rotación a partir de `date_from`:
        la siguiente a la última semana programada antes de esa fecha."""
        self.ensure_one()
        domain = [
            ('rotation_id', '=', self.id),
            ('schedule_id.state', '!=', 'cancel'),
            ('week_start', '<', date_from),
            ('slot_id', '!=', False),
        ]
        if exclude_schedule:
            domain.append(('schedule_id', '!=', exclude_schedule.id))
        last = self.env['sng.route.schedule.line'].search(
            domain, order='week_start desc, id desc', limit=1)
        if last:
            return self._slot_after(last.slot_id)
        return self._first_slot()


class SngRouteRotationSlot(models.Model):
    _name = 'sng.route.rotation.slot'
    _description = 'Semana del ciclo de rotación'
    _order = 'rotation_id, sequence, id'

    rotation_id = fields.Many2one(
        'sng.route.rotation', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    route_ids = fields.Many2many(
        'sng.sales.route', 'sng_route_rotation_slot_route_rel',
        'slot_id', 'route_id', string='Rutas',
        domain="[('active', '=', True)]")
    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('route_ids', 'route_ids.name')
    def _compute_name(self):
        for slot in self:
            slot.name = ' + '.join(slot.route_ids.mapped('name')) or '-'
