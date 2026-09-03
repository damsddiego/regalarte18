# -*- coding: utf-8 -*-
{
    "name": "SNG Envío de Mercadería",
    "version": "18.0.1.1.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory",
    "summary": "Auditoría de preparación, método de entrega y cajas por orden",
    "description": """
SNG Envío de Mercadería
========================

Registra una fotografía histórica del despacho antes de imprimir:

- Orden de venta y traslado relacionados.
- Caja actual y total de cajas.
- Método habitual del cliente y método usado en el despacho.
- Evidencia de si el método fue asignado o cambiado.
- Persona que alistó la orden.
- Historial de confirmación, actualización del cliente e impresiones.

Incluye métodos RPC idempotentes para la aplicación móvil.
""",
    "depends": [
        "mail",
        "sale_stock",
        "partner_delivery_type",
        "sale_order_shipping_method",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/envio_mercaderia_views.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        "report/envio_mercaderia_report.xml",
        "report/envio_mercaderia_templates.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
