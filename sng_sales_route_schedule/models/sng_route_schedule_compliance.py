# -*- coding: utf-8 -*-
from odoo import fields, models, tools

from odoo.addons.sng_control_visitas.models.sng_ruteros_visita import (
    RESULTADOS_COMERCIALES, RESULTADOS_NO_VISITA)

ESTADOS_CUMPLIMIENTO = [
    ('visitado', 'Visitado'),
    ('pendiente', 'Pendiente'),
    ('no_visitado', 'No visitado'),
    ('cerrado', 'Cerrado por temporada'),
]


class SngRouteScheduleCompliance(models.Model):
    """Un registro por cliente programado en una semana confirmada."""
    _name = 'sng.route.schedule.compliance'
    _description = 'Cumplimiento del cronograma de rutas'
    _auto = False
    _order = 'week_start desc, salesperson_id, route_id, partner_id'

    schedule_id = fields.Many2one('sng.route.schedule', string='Cronograma', readonly=True)
    line_id = fields.Many2one('sng.route.schedule.line', string='Semana programada', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    week_start = fields.Date(string='Semana', readonly=True)
    week_end = fields.Date(string='Hasta', readonly=True)
    salesperson_id = fields.Many2one('res.partner', string='Asesor', readonly=True)
    route_id = fields.Many2one('sng.sales.route', string='Ruta', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    estado = fields.Selection(ESTADOS_CUMPLIMIENTO, string='Estado', readonly=True)
    programados = fields.Integer(string='Programados', readonly=True)
    visitados = fields.Integer(string='Visitados', readonly=True)
    visitas = fields.Integer(string='Visitas', readonly=True)
    cumplimiento = fields.Float(
        string='% Cumplimiento', readonly=True, aggregator='avg',
        help='Promedio de clientes visitados sobre programados; los '
             'cerrados por temporada no cuentan.')
    visita_id = fields.Many2one('sng.ruteros.visita', string='Última visita', readonly=True)
    resultado_comercial = fields.Selection(
        RESULTADOS_COMERCIALES, string='Resultado', readonly=True)
    motivo_sin_venta_id = fields.Many2one(
        'sng.visita.catalogo', string='Motivo', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        no_visita = tuple(RESULTADOS_NO_VISITA)
        # Fecha de la visita en hora de Costa Rica, igual que la matriz.
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
            WITH programados AS (
                SELECT l.id AS line_id, l.schedule_id, l.company_id,
                       l.week_start, l.week_end, l.salesperson_id,
                       rel.route_id, p.id AS partner_id,
                       COALESCE(p.sng_cerrado_temporada, FALSE) AS cerrado
                  FROM sng_route_schedule_line l
                  JOIN sng_route_schedule s
                       ON s.id = l.schedule_id AND s.state = 'confirmed'
                  JOIN sng_route_schedule_line_route_rel rel ON rel.line_id = l.id
                  JOIN res_partner p ON p.sales_route_id = rel.route_id
                 WHERE p.active
                   AND p.customer_rank > 0
                   AND p.parent_id IS NULL
                   AND p.type = 'contact'
                   AND NOT COALESCE(p.is_salesperson, FALSE)
                   AND NOT COALESCE(p.sng_credit_blocked, FALSE)
                   AND NOT COALESCE(p.sng_excluir_matriz, FALSE)
                   AND NOT EXISTS (SELECT 1 FROM res_users u WHERE u.partner_id = p.id)
                   AND NOT EXISTS (SELECT 1 FROM res_company c WHERE c.partner_id = p.id)
            ), visitas AS (
                SELECT pr.line_id, pr.partner_id,
                       COUNT(v.id) FILTER (
                           WHERE v.resultado_comercial IS NULL
                              OR v.resultado_comercial NOT IN %%s) AS reales,
                       (ARRAY_AGG(v.id ORDER BY v.fecha_inicio DESC))[1] AS ultima
                  FROM programados pr
                  JOIN sng_ruteros_visita v
                       ON v.partner_id = pr.partner_id
                      AND (v.fecha_inicio AT TIME ZONE 'UTC'
                           AT TIME ZONE 'America/Costa_Rica')::date
                          BETWEEN pr.week_start AND pr.week_end
                 GROUP BY pr.line_id, pr.partner_id
            )
            SELECT ROW_NUMBER() OVER (ORDER BY pr.line_id, pr.route_id, pr.partner_id) AS id,
                   pr.schedule_id, pr.line_id, pr.company_id, pr.week_start,
                   pr.week_end, pr.salesperson_id, pr.route_id, pr.partner_id,
                   CASE WHEN COALESCE(vi.reales, 0) > 0 THEN 'visitado'
                        WHEN pr.cerrado THEN 'cerrado'
                        WHEN pr.week_end >= CURRENT_DATE THEN 'pendiente'
                        ELSE 'no_visitado' END AS estado,
                   1 AS programados,
                   CASE WHEN COALESCE(vi.reales, 0) > 0 THEN 1 ELSE 0 END AS visitados,
                   COALESCE(vi.reales, 0) AS visitas,
                   CASE WHEN COALESCE(vi.reales, 0) > 0 THEN 100.0
                        WHEN pr.cerrado THEN NULL
                        ELSE 0.0 END AS cumplimiento,
                   vi.ultima AS visita_id,
                   v.resultado_comercial,
                   v.motivo_sin_venta_id
              FROM programados pr
              LEFT JOIN visitas vi
                     ON vi.line_id = pr.line_id AND vi.partner_id = pr.partner_id
              LEFT JOIN sng_ruteros_visita v ON v.id = vi.ultima
            )
        """ % self._table, (no_visita,))
