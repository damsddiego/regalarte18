# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def _next_monday(day):
    return day + timedelta(days=(7 - day.weekday()) % 7 or 7)


class SngRouteSchedule(models.Model):
    """Cronograma de rutas de varias semanas (normalmente un trimestre)."""
    _name = 'sng.route.schedule'
    _description = 'Cronograma de rutas'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Cronograma', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, index=True,
        default=lambda self: self.env.company)
    date_from = fields.Date(
        string='Desde (lunes)', required=True, tracking=True,
        default=lambda self: _next_monday(fields.Date.context_today(self)))
    week_count = fields.Integer(
        string='Semanas', required=True, default=13, tracking=True)
    date_to = fields.Date(
        string='Hasta', compute='_compute_date_to', store=True)
    state = fields.Selection(
        [('draft', 'Borrador'), ('confirmed', 'Confirmado'),
         ('cancel', 'Cancelado')],
        string='Estado', default='draft', required=True, tracking=True,
        copy=False)
    rotation_ids = fields.Many2many(
        'sng.route.rotation', 'sng_route_schedule_rotation_rel',
        'schedule_id', 'rotation_id', string='Asesores',
        default=lambda self: self.env['sng.route.rotation'].search(
            [('company_id', '=', self.env.company.id)]),
        check_company=True)
    line_ids = fields.One2many(
        'sng.route.schedule.line', 'schedule_id', string='Semanas', copy=False)
    recipient_ids = fields.Many2many(
        'res.partner', 'sng_route_schedule_recipient_rel',
        'schedule_id', 'partner_id', string='Enviar a',
        default=lambda self: self._default_recipients(),
        help='Destinatarios del cronograma (gerencia).')
    recipient_partner_to = fields.Char(compute='_compute_recipient_partner_to')
    note = fields.Text(string='Notas')

    _sql_constraints = [
        ('week_count_range', 'check(week_count > 0 and week_count <= 26)',
         'El cronograma debe tener entre 1 y 26 semanas.'),
    ]

    @api.model
    def _default_recipients(self):
        last = self.search([('recipient_ids', '!=', False)], limit=1)
        return last.recipient_ids

    @api.depends('recipient_ids')
    def _compute_recipient_partner_to(self):
        for sched in self:
            sched.recipient_partner_to = ','.join(
                str(pid) for pid in sched.recipient_ids.ids)

    @api.depends('date_from', 'week_count')
    def _compute_date_to(self):
        for sched in self:
            sched.date_to = (
                sched.date_from + timedelta(days=7 * sched.week_count - 1)
                if sched.date_from and sched.week_count else False)

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for sched in self:
            if sched.date_from and sched.date_to:
                sched.name = _('Cronograma %(desde)s al %(hasta)s',
                               desde=sched.date_from.strftime('%d/%m/%Y'),
                               hasta=sched.date_to.strftime('%d/%m/%Y'))
            else:
                sched.name = _('Nuevo cronograma')

    @api.constrains('date_from')
    def _check_monday(self):
        for sched in self:
            if sched.date_from and sched.date_from.weekday() != 0:
                raise ValidationError(_('El cronograma debe iniciar un lunes.'))

    @api.constrains('date_from', 'week_count', 'state', 'company_id')
    def _check_overlap(self):
        for sched in self.filtered(lambda s: s.state != 'cancel'):
            if self.search_count([
                    ('id', '!=', sched.id),
                    ('company_id', '=', sched.company_id.id),
                    ('state', '!=', 'cancel'),
                    ('date_from', '<=', sched.date_to),
                    ('date_to', '>=', sched.date_from)]):
                raise ValidationError(
                    _('Ya existe otro cronograma para esas semanas.'))

    # ---------------------------------------------------------------- acciones

    def _started_lines(self):
        today = fields.Date.context_today(self)
        return self.line_ids.filtered(lambda l: l.week_start <= today)

    def action_generate(self):
        """Arma las semanas siguiendo la rotación de cada asesor."""
        for sched in self:
            if sched.state != 'draft':
                raise UserError(_('Solo se puede generar un cronograma en borrador.'))
            if not sched.rotation_ids:
                raise UserError(_('Seleccione al menos un asesor.'))
            sched.line_ids.unlink()
            vals = []
            for rot in sched.rotation_ids:
                slot = rot._next_slot_for(sched.date_from, exclude_schedule=sched)
                if not slot:
                    continue
                for week in range(sched.week_count):
                    vals.append({
                        'schedule_id': sched.id,
                        'rotation_id': rot.id,
                        'salesperson_id': rot.salesperson_id.id,
                        'week_start': sched.date_from + timedelta(weeks=week),
                        'slot_id': slot.id,
                        'route_ids': [(6, 0, slot.route_ids.ids)],
                    })
                    slot = rot._slot_after(slot)
            self.env['sng.route.schedule.line'].create(vals)
        return True

    def action_confirm(self):
        for sched in self:
            if not sched.line_ids:
                raise UserError(_('Genere las semanas antes de confirmar.'))
            if sched.line_ids.filtered(lambda l: not l.route_ids):
                raise UserError(_('Todas las semanas deben tener al menos una ruta.'))
            sched.state = 'confirmed'
        self.env['sng.control.visitas.linea']._sng_recalcular_por_cronograma(self)
        return True

    def action_draft(self):
        for sched in self:
            if sched._started_lines():
                raise UserError(_(
                    'El cronograma ya tiene semanas iniciadas; no puede volver '
                    'a borrador. Las semanas futuras se ajustan desde un nuevo '
                    'cronograma.'))
            sched.state = 'draft'
        self.env['sng.control.visitas.linea']._sng_recalcular_por_cronograma(self)
        return True

    def action_cancel(self):
        for sched in self:
            if sched.state == 'confirmed' and sched._started_lines():
                raise UserError(_('No se puede cancelar un cronograma con semanas iniciadas.'))
            sched.state = 'cancel'
        self.env['sng.control.visitas.linea']._sng_recalcular_por_cronograma(self)
        return True

    def action_send(self):
        self.ensure_one()
        template = self.env.ref(
            'sng_sales_route_schedule.mail_template_route_schedule',
            raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': self.ids,
                'default_template_id': template.id if template else False,
                'default_composition_mode': 'comment',
                'force_email': True,
            },
        }

    def action_print(self):
        return self.env.ref(
            'sng_sales_route_schedule.action_report_route_schedule'
        ).report_action(self)

    def action_view_compliance(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'sng_sales_route_schedule.action_route_schedule_compliance')
        action['domain'] = [('schedule_id', '=', self.id)]
        return action

    # ---------------------------------------------------------------- reporte

    def _report_weeks(self):
        """Semanas ordenadas con sus líneas por asesor (para el PDF/correo)."""
        self.ensure_one()
        people = self.line_ids.mapped('salesperson_id').sorted('name')
        weeks = []
        for start in sorted(set(self.line_ids.mapped('week_start'))):
            lines = self.line_ids.filtered(lambda l: l.week_start == start)
            weeks.append({
                'start': start,
                'end': start + timedelta(days=6),
                'cells': [
                    lines.filtered(lambda l: l.salesperson_id == p)
                    for p in people
                ],
            })
        return people, weeks


class SngRouteScheduleLine(models.Model):
    _name = 'sng.route.schedule.line'
    _description = 'Semana del cronograma de rutas'
    _order = 'week_start, salesperson_id, id'
    _check_company_auto = True

    schedule_id = fields.Many2one(
        'sng.route.schedule', string='Cronograma', required=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='schedule_id.company_id', store=True, index=True)
    state = fields.Selection(related='schedule_id.state', store=True)
    rotation_id = fields.Many2one(
        'sng.route.rotation', string='Rotación', ondelete='set null')
    salesperson_id = fields.Many2one(
        'res.partner', string='Asesor', required=True, index=True,
        domain="[('is_salesperson', '=', True)]")
    week_start = fields.Date(string='Semana (lunes)', required=True, index=True)
    week_end = fields.Date(
        string='Hasta', compute='_compute_week_end', store=True, index=True)
    week_number = fields.Char(string='Semana', compute='_compute_week_end', store=True)
    slot_id = fields.Many2one(
        'sng.route.rotation.slot', string='Posición del ciclo',
        domain="[('rotation_id', '=', rotation_id)]", ondelete='set null')
    route_ids = fields.Many2many(
        'sng.sales.route', 'sng_route_schedule_line_route_rel',
        'line_id', 'route_id', string='Rutas')
    route_names = fields.Char(
        string='Rutas programadas', compute='_compute_route_names')
    note = fields.Char(string='Nota', help='Feriados, giras especiales, etc.')
    started = fields.Boolean(string='Iniciada', compute='_compute_started')
    client_count = fields.Integer(
        string='Clientes', compute='_compute_client_count')

    @api.depends('week_start')
    def _compute_week_end(self):
        for line in self:
            if line.week_start:
                line.week_end = line.week_start + timedelta(days=6)
                line.week_number = 'S%02d %s' % (
                    line.week_start.isocalendar()[1], line.week_start.year)
            else:
                line.week_end = False
                line.week_number = False

    @api.depends('route_ids')
    def _compute_route_names(self):
        for line in self:
            line.route_names = ' + '.join(line.route_ids.mapped('name'))

    def _compute_started(self):
        today = fields.Date.context_today(self)
        for line in self:
            line.started = bool(line.week_start and line.week_start <= today)

    @api.depends('route_ids')
    def _compute_client_count(self):
        Partner = self.env['res.partner']
        for line in self:
            line.client_count = Partner.search_count([
                ('sales_route_id', 'in', line.route_ids.ids),
                ('customer_rank', '>', 0),
                ('parent_id', '=', False),
            ]) if line.route_ids else 0

    @api.onchange('slot_id')
    def _onchange_slot_id(self):
        if self.slot_id:
            self.route_ids = self.slot_id.route_ids

    @api.constrains('week_start')
    def _check_monday(self):
        for line in self:
            if line.week_start.weekday() != 0:
                raise ValidationError(_('La semana debe iniciar un lunes.'))

    @api.constrains('salesperson_id', 'week_start', 'schedule_id')
    def _check_unique_week(self):
        for line in self:
            if self.search_count([
                    ('id', '!=', line.id),
                    ('schedule_id', '=', line.schedule_id.id),
                    ('salesperson_id', '=', line.salesperson_id.id),
                    ('week_start', '=', line.week_start)]):
                raise ValidationError(_(
                    'El asesor %(asesor)s ya tiene programada la semana del %(semana)s.',
                    asesor=line.salesperson_id.name,
                    semana=line.week_start.strftime('%d/%m/%Y')))

    def _check_editable(self):
        today = fields.Date.context_today(self)
        for line in self:
            if line.schedule_id.state == 'confirmed' and line.week_start <= today:
                raise UserError(_(
                    'La semana del %(semana)s de %(asesor)s ya inició y no se '
                    'puede modificar.',
                    semana=line.week_start.strftime('%d/%m/%Y'),
                    asesor=line.salesperson_id.name))

    def write(self, vals):
        if set(vals) - {'note'}:
            self._check_editable()
        res = super().write(vals)
        if {'route_ids', 'week_start'} & set(vals):
            self.env['sng.control.visitas.linea']._sng_recalcular_por_cronograma(
                self.schedule_id.filtered(lambda s: s.state == 'confirmed'))
        return res

    def unlink(self):
        self._check_editable()
        return super().unlink()

    def action_skip(self):
        """Salta la posición de esta semana: esta y las siguientes semanas del
        asesor en el cronograma avanzan una posición del ciclo."""
        self.ensure_one()
        if not self.rotation_id or not self.slot_id:
            raise UserError(_('La semana no está ligada a una rotación.'))
        lines = self.schedule_id.line_ids.filtered(
            lambda l: l.rotation_id == self.rotation_id
            and l.week_start >= self.week_start
        ).sorted('week_start')
        lines._check_editable()
        slot = self.rotation_id._slot_after(self.slot_id)
        for line in lines.with_context(sng_skip_matrix_recalc=True):
            line.write({'slot_id': slot.id, 'route_ids': [(6, 0, slot.route_ids.ids)]})
            slot = self.rotation_id._slot_after(slot)
        if self.schedule_id.state == 'confirmed':
            self.env['sng.control.visitas.linea']._sng_recalcular_por_cronograma(
                self.schedule_id)
        return True
