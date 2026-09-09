# -*- coding: utf-8 -*-
import logging

from odoo import fields

_logger = logging.getLogger(__name__)

LOGIN_TELEVENTAS = 'ventas1@regalartecr.com'
LOGINS_GERENCIA = ('admin1@regalartecr.com', 'gerencia@regalartecr.com')


def post_init_hook(env):
    """Configuración inicial con los datos reales de Regalarte.

    Todo es idempotente y tolerante: si un usuario o ruta no existe (por
    ejemplo en una base de pruebas) simplemente se omite.
    """
    Users = env['res.users']
    grupo_user = env.ref('sng_control_visitas.group_control_visitas_user')
    grupo_manager = env.ref('sng_control_visitas.group_control_visitas_manager')

    natalia = Users.search([('login', '=', LOGIN_TELEVENTAS)], limit=1)
    if natalia:
        natalia.write({'groups_id': [(4, grupo_user.id)]})
        for company in env['res.company'].search([]):
            if not company.sng_televentas_user_id:
                company.sng_televentas_user_id = natalia
    gerencia = Users.search([('login', 'in', list(LOGINS_GERENCIA))])
    if gerencia:
        gerencia.write({'groups_id': [(4, grupo_manager.id)]})
    env.ref('base.user_admin').write({'groups_id': [(4, grupo_manager.id)]})

    # Tipo de atención por nombre de ruta (las rutas TELEVENTAS / OFICINA /
    # CORPORATIVO no se visitan en sitio).
    Route = env['sng.sales.route'].with_context(active_test=False)
    for route in Route.search([]):
        nombre = (route.name or '').strip().upper()
        if 'TELEVENTAS' in nombre:
            route.sng_tipo_atencion = 'televentas'
        elif nombre in ('OFICINA', 'CORPORATIVO'):
            route.sng_tipo_atencion = 'oficina'
        elif 'INACTIVO' in nombre or 'INCOBRABLE' in nombre:
            route.sng_frecuencia_visita = 'sin_visita'

    # Matriz del mes actual para que el menú no aparezca vacío.
    hoy = fields.Date.today()
    Linea = env['sng.control.visitas.linea']
    for company in env['res.company'].search([]):
        try:
            Linea._sng_generar_mes(hoy, company)
        except Exception:  # noqa: BLE001
            _logger.exception(
                'sng_control_visitas: no se pudo generar la matriz inicial '
                'para %s', company.name)
