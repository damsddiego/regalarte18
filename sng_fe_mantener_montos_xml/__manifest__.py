# -*- coding: utf-8 -*-
{
    "name": "SNG FE: mantener montos del XML al cambiar producto",
    "summary": "Por proveedor, conserva precio, cantidad e impuestos del XML al asignar producto en la línea",
    "description": """
Las facturas de proveedor importadas desde el XML de Hacienda traen precio, cantidad
e impuestos exactos en cada línea, pero sin producto. Al asignar un producto (por
ejemplo un servicio de costo en destino) Odoo recalcula el precio y los impuestos
desde el producto y se pierde el monto del XML.

Este módulo agrega una casilla en el proveedor: cuando está marcada, las líneas que
vienen del XML conservan precio unitario, cantidad e impuestos al cambiar el producto.
La etiqueta y la cuenta contable siguen la regla normal de Odoo.
""",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "cr_electronic_invoice",
        "cr_import_vendor_bills",
    ],
    "data": [
        "views/res_partner_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
