# -*- coding: utf-8 -*-
{
    "name": "Notificación de Falta de Stock en Entregas",
    "version": "18.0.1.0.0",
    "category": "Inventory/Stock",
    "summary": "Notifica a usuarios configurados cuando una entrega no puede validarse por falta de stock.",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["stock", "mail"],
    "data": [
        "data/mail_template_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
