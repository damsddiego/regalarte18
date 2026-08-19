# -*- coding: utf-8 -*-
{
    "name": "SNG Consolidated Customer Payment",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Distribuye un cobro real entre facturas de multiples companias",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/res_config_settings_views.xml",
        "views/consolidated_customer_payment_bridge_views.xml",
        "views/consolidated_customer_payment_views.xml",
        "views/account_payment_views.xml",
        "views/account_move_views.xml",
        "wizard/consolidated_customer_payment_load_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
