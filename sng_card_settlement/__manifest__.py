# -*- coding: utf-8 -*-
{
    "name": "SNG Card Settlement",
    "version": "18.0.1.1.0",
    "category": "Accounting",
    "summary": "Liquidaciones diarias de pagos con tarjeta",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/res_config_settings_views.xml",
        "views/account_journal_views.xml",
        "views/account_payment_views.xml",
        "wizard/card_settlement_wizard_views.xml",
        "views/card_settlement_views.xml",
    ],
    "installable": True,
    "application": False,
}
