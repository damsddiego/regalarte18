{
    "name": "SNG Custom Name Payment",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Search and show partner commercial name on payments",
    "author": "SNG",
    "depends": [
        "account",
        "customer_sequence",
        "sng_custom_name_partner",
    ],
    "data": [
        "views/account_payment_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
