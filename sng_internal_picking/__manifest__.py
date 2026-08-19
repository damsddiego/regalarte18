# -*- coding: utf-8 -*-
{
    "name": "Auto validacion de traslados",
    "version": "18.0.1.0.0",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Inventory",
    "summary": "Auto valida traslados segun tipo de operacion configurado.",
    "depends": ["stock"],
    "data": [
        "views/stock_picking_type_view.xml",
        "views/stock_picking_view.xml",
        "security/ir.model.access.csv",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
