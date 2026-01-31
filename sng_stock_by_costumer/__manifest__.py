{
    'name': 'Stock by Customer',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Report showing inventory value by customer location',
    'description': """
Stock by Customer Report
========================
This module provides a report that shows the total inventory value
for each customer that has an assigned warehouse location.

Features:
---------
* Lists all customers with assigned sales locations (sale_location_id)
* Calculates total inventory value per customer location
* Includes child locations in calculations
* Export report to Excel format
    """,
    'author': 'SNG',
    'website': '',
    'depends': [
        'base',
        'stock',
        'stock_account',
        'sale_stock_sng',  # Required for sale_location_id field
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/stock_by_customer_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
