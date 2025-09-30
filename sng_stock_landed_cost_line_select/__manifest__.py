# -*- coding: utf-8 -*-
{
    "name": "Landed Costs por Líneas",
    "version": "18.0.1.0.0",
    "summary": "Aplicar costos de destino solo a líneas (stock.moves) seleccionadas",
    "category": "Inventory",
    "author": "SNG Cloud SRL",
    "license": "LGPL-3",
    "depends": ["stock", "stock_landed_costs"],
    "data": [
        "views/stock_landed_cost_views.xml",
    ],
    "installable": True,
    "application": False
}
