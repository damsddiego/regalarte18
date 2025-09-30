{
    "name": "Partner Delivery Type",
    "version": "18.0.3.0.0",
    "summary": "Campo 'Tipo de entrega' configurable y multi-compañía en Contactos",
    "author": "SNG Cloud SRL",
    "website": "https://sngcloud.cr",
    "category": "Contacts",
    "license": "LGPL-3",
    "depends": ["base", "contacts", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/res_partner_delivery_type_rules.xml",
        "views/delivery_type_views.xml",
        "views/res_partner_views.xml"
    ],
    "installable": True,
    "application": False
}
