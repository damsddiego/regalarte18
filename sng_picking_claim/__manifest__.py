# -*- coding: utf-8 -*-
{
    "name": "SNG Reclamo de Alistado",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory",
    "summary": "Bloqueo atómico de órdenes y traslados tomados desde la app móvil",
    "description": """
SNG Reclamo de Alistado
=======================

Evita que dos operarios trabajen el mismo documento al mismo tiempo.

La aplicación móvil se conecta a Odoo con una única cuenta técnica, por lo que
el servidor no puede distinguir a un operario de otro. Este módulo resuelve eso
registrando explícitamente quién tiene tomado cada documento:

- Campos de reclamo en la orden de venta y en el traslado: operario, dispositivo
  y momento de la toma.
- Método RPC de reclamo que bloquea la fila en base de datos, verifica que el
  documento siga libre y en la etapa esperada, y recién entonces cambia la etapa.
  Dos solicitudes simultáneas no pueden ganar las dos.
- Registro de dispositivos: cada tableta se identifica con un código propio y un
  nombre legible asignado una sola vez. Odoo manda sobre el nombre.
- Historial de reclamos como pista de auditoría real, en lugar de texto libre
  dentro del chatter.
- Liberación manual por parte de un responsable para recuperar documentos cuyo
  dispositivo se perdió o se dañó.

Vencimiento opcional del reclamo mediante el parámetro de sistema
``sng_picking_claim.timeout_minutes`` (0 lo desactiva, que es el valor por
defecto).
""",
    "depends": [
        "mail",
        "sale_stock",
        "eg_sales_order_stages",
        "sng_stock_picking_stages",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/config_parameter.xml",
        "views/picking_device_views.xml",
        "views/picking_claim_views.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        "views/menus.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
