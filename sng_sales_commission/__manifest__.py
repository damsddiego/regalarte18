# -*- coding: utf-8 -*-
{
    "name": "SNG Sales Commission",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "summary": "Comisiones configurables por cobro aplicado y cumplimiento de meta",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "account",
        "sales_commission_omax",
        "sng_invoice_report",
    ],
    "data": [
        "security/group_security.xml",
        "security/ir.model.access.csv",
        "wizard/commission_generate_wizard_views.xml",
        "views/commission_plan_views.xml",
        "views/commission_target_views.xml",
        "views/commission_settlement_views.xml",
        "report/commission_report.xml",
    ],
    "external_dependencies": {
        "python": ["xlsxwriter"],
    },
    "installable": True,
    "application": True,
}
