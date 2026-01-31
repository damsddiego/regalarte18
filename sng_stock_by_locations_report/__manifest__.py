{
    'name': 'SNG Stock By Customer Location',
    'version': '18.0.1.0.0',
    'category': 'Warehouse',
    'summary': 'Customer inventory value report by location.',
    'description': """
        This module provides a comprehensive view of inventory values by customer locations.
        Features:
        - View total inventory value per customer
        - Display unique_id and complete_name from res.partner
        - Calculate total value based on sales prices
        - Support for XLSX, PDF and on-screen views
        - Filter by customers and date ranges
    """,
    'author': 'SNG Solutions',
    'depends': ['base', 'stock', 'product', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_location_views.xml',
        'wizard/sng_stock_customer_report_views.xml',
        'report/sng_stock_customer_report.xml',
        'report/sng_stock_customer_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sng_stock_by_locations_report/static/src/js/action_manager.js',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
