# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.sng_control_visitas.tests.common import ControlVisitasCommon


@tagged('post_install', '-at_install', 'sng_sales_route_schedule')
class TestRouteSchedule(ControlVisitasCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Route = cls.env['sng.sales.route']
        cls.ruta_b = Route.create({'name': 'RUTA B', 'code': 'TB',
                                   'salesperson_id': cls.agente.id})
        cls.ruta_c = Route.create({'name': 'RUTA C', 'code': 'TC',
                                   'salesperson_id': cls.agente.id})
        cls.rotacion = cls.env['sng.route.rotation'].create({
            'salesperson_id': cls.agente.id,
            'slot_ids': [
                (0, 0, {'sequence': 10, 'route_ids': [(6, 0, (cls.ruta | cls.ruta_c).ids)]}),
                (0, 0, {'sequence': 20, 'route_ids': [(6, 0, cls.ruta_b.ids)]}),
            ],
        })
        cls.cliente_b = cls.env['res.partner'].create({
            'name': 'Cliente B', 'customer_rank': 1,
            'sales_route_id': cls.ruta_b.id,
            'assigned_salesperson_id': cls.agente.id,
            'company_id': cls.company.id,
        })
        today = fields.Date.context_today(cls.env.user)
        cls.lunes = today - timedelta(days=today.weekday())

    def _cronograma(self, desde, semanas=4):
        sched = self.env['sng.route.schedule'].create({
            'date_from': desde, 'week_count': semanas,
            'rotation_ids': [(6, 0, self.rotacion.ids)],
        })
        sched.action_generate()
        return sched

    def test_genera_siguiendo_rotacion_y_continua(self):
        sched = self._cronograma(self.lunes + timedelta(weeks=1), 3)
        rutas = [l.route_ids for l in sched.line_ids.sorted('week_start')]
        self.assertEqual(rutas, [self.ruta | self.ruta_c, self.ruta_b, self.ruta | self.ruta_c])
        # El siguiente cronograma continúa donde quedó el anterior.
        sched2 = self._cronograma(sched.date_to + timedelta(days=1), 1)
        self.assertEqual(sched2.line_ids.route_ids, self.ruta_b)

    def test_debe_iniciar_lunes_y_no_traslaparse(self):
        with self.assertRaises(ValidationError):
            self.env['sng.route.schedule'].create({
                'date_from': self.lunes + timedelta(days=1), 'week_count': 1})
        self._cronograma(self.lunes + timedelta(weeks=1), 2)
        with self.assertRaises(ValidationError):
            self._cronograma(self.lunes + timedelta(weeks=2), 2)

    def test_saltar_posicion_corre_semanas(self):
        sched = self._cronograma(self.lunes + timedelta(weeks=1), 3)
        lines = sched.line_ids.sorted('week_start')
        lines[0].action_skip()
        self.assertEqual(
            [l.route_ids for l in lines],
            [self.ruta_b, self.ruta | self.ruta_c, self.ruta_b])

    def test_semana_iniciada_no_se_modifica(self):
        sched = self._cronograma(self.lunes, 2)
        sched.action_confirm()
        actual = sched.line_ids.filtered(lambda l: l.week_start == self.lunes)
        with self.assertRaises(UserError):
            actual.route_ids = self.ruta_b
        actual.note = 'Feriado'  # la nota sí se puede anotar
        with self.assertRaises(UserError):
            sched.action_draft()

    def test_matriz_toma_semana_programada(self):
        sched = self._cronograma(self.lunes, 1)
        sched.action_confirm()
        Linea = self.env['sng.control.visitas.linea']
        Linea._sng_generar_mes(self.lunes)
        periodo = self.lunes.strftime('%Y-%m')
        linea = Linea.search([('partner_id', '=', self.cliente.id), ('periodo', '=', periodo)])
        self.assertEqual(linea.fecha_visita_programada,
                         max(self.lunes, self.lunes.replace(day=1)))
        # RUTA B está en la rotación pero no se programó este mes: no se espera.
        linea_b = Linea.search([('partner_id', '=', self.cliente_b.id), ('periodo', '=', periodo)])
        self.assertFalse(linea_b.fecha_visita_programada)
        self.assertFalse(linea_b.cliente_desatendido)

    def test_cumplimiento(self):
        sched = self._cronograma(self.lunes, 1)
        sched.action_confirm()
        self.cliente2.sng_cerrado_temporada = True
        self._visita(self.cliente, fecha_inicio=datetime.combine(
            self.lunes, datetime.min.time()) + timedelta(hours=16))
        self.env.flush_all()
        rows = self.env['sng.route.schedule.compliance'].search([('schedule_id', '=', sched.id)])
        por_cliente = {r.partner_id: r.estado for r in rows}
        self.assertEqual(por_cliente[self.cliente], 'visitado')
        self.assertEqual(por_cliente[self.cliente2], 'cerrado')
        self.assertNotIn(self.cliente_b, por_cliente)

    def test_reporte_pdf(self):
        sched = self._cronograma(self.lunes + timedelta(weeks=1), 2)
        html = self.env['ir.actions.report']._render_qweb_html(
            'sng_sales_route_schedule.action_report_route_schedule', sched.ids)[0]
        self.assertIn(b'RUTA B', html)
