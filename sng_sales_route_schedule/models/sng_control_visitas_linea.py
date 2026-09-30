# -*- coding: utf-8 -*-
from datetime import date

from odoo import api, models


class SngControlVisitasLinea(models.Model):
    _inherit = 'sng.control.visitas.linea'

    @api.model
    def _sng_programacion_externa(self, partners, fecha_desde, fecha_hasta,
                                  company):
        """La semana del cronograma confirmado es la visita programada.

        Solo aplica cuando hay un cronograma confirmado que cubre el
        período. Los clientes de rutas manejadas por rotación que no se
        programaron en el período, y los cerrados por temporada, no se
        esperan (no cuentan como desatendidos)."""
        plan, sin_plan = super()._sng_programacion_externa(
            partners, fecha_desde, fecha_hasta, company)
        lines = self.env['sng.route.schedule.line'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'confirmed'),
            ('week_start', '<=', fecha_hasta),
            ('week_end', '>=', fecha_desde),
        ])
        if not lines:
            return plan, sin_plan
        rutas_rotacion = self.env['sng.route.rotation'].search([
            ('company_id', '=', company.id),
        ]).slot_ids.route_ids
        fecha_ruta = {}
        for line in lines:
            inicio = max(line.week_start, fecha_desde)
            for ruta in line.route_ids:
                fecha_ruta[ruta.id] = min(fecha_ruta.get(ruta.id, inicio), inicio)
        for partner in partners:
            ruta = partner.sales_route_id
            if partner.sng_cerrado_temporada and ruta in rutas_rotacion:
                sin_plan.add(partner.id)
            elif ruta.id in fecha_ruta:
                plan.setdefault(partner.id, []).append(fecha_ruta[ruta.id])
            elif ruta in rutas_rotacion:
                sin_plan.add(partner.id)
        return plan, sin_plan

    @api.model
    def _sng_recalcular_por_cronograma(self, schedules):
        """Regenera los meses ya generados de la matriz que cubre el
        cronograma, para reflejar la programación sin esperar al cron."""
        if self.env.context.get('sng_skip_matrix_recalc') or not schedules:
            return
        for sched in schedules:
            periodos = self.sudo().read_group(
                [('company_id', '=', sched.company_id.id),
                 ('fecha_desde', '<=', sched.date_to),
                 ('fecha_hasta', '>=', sched.date_from)],
                ['periodo'], ['periodo'], lazy=False)
            for grupo in periodos:
                anio, mes = grupo['periodo'].split('-')
                self.sudo()._sng_generar_mes(date(int(anio), int(mes), 1),
                                      sched.company_id)
