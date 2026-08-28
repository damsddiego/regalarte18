# -*- coding: utf-8 -*-
{
    'name': 'Estado de Cuenta para Cliente',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Accounting',
    'summary': 'Estado de cuenta individual, claro y multimoneda para enviar al cliente.',
    'description': """
Estado de Cuenta para Cliente
=============================

Salida paralela al reporte interno de estado de cuenta. Genera una vista previa
HTML y un PDF individual por cliente, con documentos abiertos, vencimiento,
antigüedad y saldos separados por moneda.
    """,
    'author': 'SNG Cloud',
    'website': 'https://www.sngcloud.com',
    'license': 'OPL-1',
    'depends': [
        'sng_customer_statement',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/customer_statement_client_wizard_view.xml',
        'report/customer_statement_client_report.xml',
        'report/customer_statement_client_template.xml',
        'views/menu_views.xml',
        'views/replacement_integration.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
}
