{
    "name": "Stock Picking Stages",
    "version": "18.0.1.0.0",
    "author": "SNG",
    "license": "LGPL-3",
    "summary": "Etapas personalizables para transferencias de inventario",
    "description": """
        Agrega un campo de etapa independiente al modelo stock.picking,
        permitiendo gestionar flujos de trabajo internos para recepciones,
        entregas y transferencias internas sin alterar el estado nativo de Odoo.
    """,
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_picking_stage_view.xml",
        "views/stock_picking_view.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "category": "Inventory",
}
