# -*- coding: utf-8 -*-
{
    "name": "SNG Importación de Clientes a Listas de Correo",
    "version": "18.0.1.0.0",
    "author": "SNG",
    "license": "LGPL-3",
    "category": "Marketing/Email Marketing",
    "summary": "Importa clientes a listas de correo por etiqueta, ruta, provincia o actividad económica",
    "depends": [
        "mass_mailing",
        "sng_sales_routes",
        "sale_stock_sng",
        "sng_cxc_report",
        "cr_electronic_invoice",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/mailing_contact_views.xml",
        "wizard/mailing_import_wizard_views.xml",
    ],
    "installable": True,
}
