# -*- coding: utf-8 -*-
{
    'name' : 'Reporte de Impuestos Contables',
    'version':'18.0.1.0',
    'category': 'Accounting,Sales,Purchases',
    'sequence': 1,
    'author': 'OMAX Informatics',
    'website': 'https://www.omaxinformatics.com',
    'description' : '''
            Este módulo permite generar reportes de impuestos de ventas y compras en formato PDF y Excel.
			''',
    'depends' : ['account','sale','purchase'],
    'data':[
        'security/ir.model.access.csv',
        'wizard/tax_report_wizard.xml',
        'wizard/tax_report_wizard_sales.xml',
        'wizard/tax_report_wizard_purchases.xml',
        'security/ir_model_access.xml',
        'report/report.xml',
        'report/report_menu.xml',
    ],
    'images':['static/description/banner.png'],
    'license':'OPL-1', 
    'currency':'USD',
    'price': 35.00,
    'demo':[],
    'test':[],
    'application':True,
    'installable':True,
    'auto_install':False,
    'pre_init_hook': 'pre_init_check',
    'module_type': 'official',
    'summary': '''
    Reporte detallado de impuestos para ventas y compras, con filtros por contactos,
    categorías de producto, productos, equipos de ventas, vendedores e impuestos.
    Permite generar reportes en PDF y Excel con soporte multi-compañía y multi-moneda.
    ''',
}
