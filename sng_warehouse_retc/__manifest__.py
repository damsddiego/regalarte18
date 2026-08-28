# -*- coding: utf-8 -*-
{
    "name": "RETC automático por almacén",
    "version": "18.0.1.0.0",
    "category": "Inventory",
    "summary": "Crea automáticamente el tipo de operación RETC al crear un almacén.",
    "description": """
        Crea automáticamente un tipo de operación de inventario con
        Sequence Code 'RETC' (Retorno de Cliente) cada vez que se crea
        un nuevo almacén en la compañía.
    """,
    "author": "SNG",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [],
    "installable": True,
    "application": False,
}
