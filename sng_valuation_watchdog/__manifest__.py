# -*- coding: utf-8 -*-
{
    "name": "SNG Vigilante de Valoración de Inventario",
    "version": "18.0.1.1.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory/Inventory",
    "summary": "Cron diario que detecta anomalías de valoración de inventario, avisa por correo "
               "y las muestra en Inventario > Informes > Anomalías de valoración",
    "depends": ["stock_account", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/valuation_anomaly_views.xml",
        "data/ir_cron.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
