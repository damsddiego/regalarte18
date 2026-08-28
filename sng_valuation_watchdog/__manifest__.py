# -*- coding: utf-8 -*-
{
    "name": "SNG Vigilante de Valoración de Inventario",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory/Inventory",
    "summary": "Cron diario que detecta anomalías de valoración de inventario y avisa por correo",
    "depends": ["stock_account", "mail"],
    "data": [
        "data/ir_cron.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
