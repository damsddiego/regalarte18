# -*- coding: utf-8 -*-
"""Rotaciones iniciales de Regalarte según el Plan de Rutas 2026 de Andrey.

Cada tupla es una semana del ciclo (códigos de ruta); se crean solo si las
rutas existen y aún no hay rotaciones. `inicio` es la posición del ciclo con
la que arranca el primer cronograma (semana del 5 de octubre de 2026).
"""

ROTACIONES = [
    {'rutas': [('0180', '0220'), ('0200',), ('0190',), ('0180',)], 'inicio': 1},
    {'rutas': [('0040',), ('0080',), ('0210',), ('0050',)], 'inicio': 1},
    {'rutas': [('0110',), ('0160',), ('0170',), ('0090',), ('0070',)], 'inicio': 0},
]


def post_init_hook(env):
    Rotation = env['sng.route.rotation'].sudo()
    if Rotation.search_count([]):
        return
    Route = env['sng.sales.route'].sudo()
    for definicion in ROTACIONES:
        semanas = []
        for codigos in definicion['rutas']:
            rutas = Route.search([('code', 'in', list(codigos))])
            if len(rutas) != len(codigos):
                semanas = []
                break
            semanas.append(rutas)
        asesor = semanas and semanas[0].salesperson_id[:1]
        if not asesor:
            continue
        rot = Rotation.create({
            'salesperson_id': asesor.id,
            'company_id': (semanas[0].company_id[:1] or env.company).id,
            'slot_ids': [
                (0, 0, {'sequence': (i + 1) * 10, 'route_ids': [(6, 0, rutas.ids)]})
                for i, rutas in enumerate(semanas)
            ],
        })
        slots = rot._ordered_slots()
        rot.start_slot_id = slots[definicion['inicio']]
