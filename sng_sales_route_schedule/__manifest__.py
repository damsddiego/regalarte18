# -*- coding: utf-8 -*-
{
    "name": "SNG Cronograma de Rutas",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Programación semanal de rutas por asesor, cumplimiento de "
               "visitas y ventas por ruta",
    "description": """
Extiende las Rutas / Territorios de Venta con la programación semanal:

* Rotación de rutas por asesor (una o varias rutas por semana).
* Cronograma trimestral generado desde la rotación, ajustable antes de que
  inicie cada semana y bloqueado una vez iniciada.
* Envío del cronograma a gerencia por correo (PDF).
* La semana programada alimenta la visita programada de la Matriz de
  Control; las rutas no programadas en el mes no se esperan.
* Cumplimiento: clientes programados contra visitados por asesor, ruta y
  semana, con resultado/motivo de la visita y clientes cerrados por
  temporada.
* Ventas por ruta semanal, mensual y anual.
""",
    "author": "SNG",
    "website": "https://sngcloud.cr",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "account",
        "sng_sales_routes",
        "sng_ruteros_pagos",
        "sng_control_visitas",
    ],
    "data": [
        "security/sng_route_schedule_security.xml",
        "security/ir.model.access.csv",
        "report/sng_route_schedule_report.xml",
        "data/mail_template_data.xml",
        "views/sng_route_rotation_views.xml",
        "views/sng_route_schedule_views.xml",
        "views/sng_route_schedule_compliance_views.xml",
        "views/sng_route_sales_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
