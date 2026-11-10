# -*- coding: utf-8 -*-

{
    "name": "SNG Facturación por Cliente Mensual",
    "version": "18.0.1.1.0",
    "category": "Accounting/Reporting",
    "summary": (
        "Excel de facturación por cliente y mes: subtotal, descuento, "
        "notas de crédito, VNAI, impuesto y total"
    ),
    "author": "SNG",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale",
        "report_xlsx",
        "customer_sequence",
        "sng_custom_name_partner",
        "sales_commission_omax",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "report/facturacion_cliente_mensual_actions.xml",
        "wizard/facturacion_cliente_mensual_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
