{
    'name': 'Stock By Location',
    'version': '18.0.0.3',
    'category': 'Warehouse',
    'summary': """Real-time inventory tracking. """
               """Customizable PDF and XLSX reports. """
               """Purchase/Sales Stock By Location.  """
               """Multi-Company Support.""",
    'description': """This module enhances stock management by offering real-time inventory tracking and detailed insights across multiple locations."""
                   """ensuring streamlined and accurate inventory control.""" 
                   """With interactive pivot, tree, and graph views, it's easy to analyze inventory for multiple companies."""
                   """Stock By Location in purchase and sales orders, and enhanced visibility in product variant management.""",
    'author': 'Hocine Dev',
    'company': 'H-TECH Solutions',
    'maintainer': 'Hocine Dev',
    'price': '15.0',
    'currency': 'USD',
    #'website': 'https://www.HocineDev.com',
    'depends': ['base', 'stock', 'product', 'sale_management', 'purchase'],
    'data': [
        'security/account_security.xml',
        'security/ir.model.access.csv',
        'data/measure_options.xml',
        'views/product_analysis_report.xml',
        'views/product_product_stock_locations.xml',
        'views/sale_order_line_stock_locations.xml',
        'views/purchase_order_line_stock_locations.xml',
        'report/stock_by_locations_report.xml',
        'report/stock_by_locations_report_templates.xml',
        'wizard/stock_locations_wizard_views.xml',
        'wizard/stock_by_locations_report_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_by_locations_report/static/src/js/action_manager.js',
             ],
    },
    'images': ['static/description/banner.png'],
    'license': 'OPL-1',
    'installable': True,
    'application': False,
    'auto_install': False,
}
