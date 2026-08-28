{
    'name': 'SNG Account Journal API',
    'version': '18.0.1.2.0',
    'summary': 'Adds API filtering for journals and expense account assignment to partners',
    'description': """
        This module adds:
        - A boolean field 'Incluir en App' (include_in_app) to Account Journals
          for external API filtering.
        - An expense account field on partners/customers to assign a default
          expense account.
        - Automatic application of partner's expense account on vendor bill lines
          (takes priority over product's expense account).
    """,
    'category': 'Accounting',
    'author': 'SNG CLOUD',
    'depends': ['account'],
    'data': [
        'views/account_journal_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
