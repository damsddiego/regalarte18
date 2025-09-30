# -*- coding: utf-8 -*-
{
    "name": "Partner Client Code (Per Company)",
    "version": "18.0.1.0.3",
    "author": "SNG Cloud",
    "website": "https://sngcloud.com",
    "category": "Contacts",
    "summary": "Código de cliente autogenerado por compañía y buscable (compat 17/18, batch-safe)",
    "depends": ["base"],
    "data": [
        "data/ir_sequence_data.xml",
        "views/res_partner_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
