# -*- coding: utf-8 -*-
{
    "name": "SNG - Reporte Facturas y Pagos No Conciliados",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Reporte de facturas pendientes y pagos confirmados no conciliados",
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["base", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/wizard_views.xml",
        "views/reconcile_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
