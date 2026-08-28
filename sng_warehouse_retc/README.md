# sng_warehouse_retc

## Descripción

Módulo para Odoo 18 que crea automáticamente el tipo de operación de inventario **RETC** (Retorno de Cliente) cada vez que se crea un nuevo almacén (`stock.warehouse`) en la compañía.

## Funcionamiento

- Hereda el modelo `stock.warehouse`.
- Sobrescribe el método `create` para que, inmediatamente después de crear un almacén, se genere un `stock.picking.type` asociado.
- El tipo de operación tiene:
  - **Sequence Code:** `RETC`
  - **Code:** `internal`
  - **Nombre:** `Retorno de Cliente (<Nombre del almacén>)`
  - **Ubicación origen:** `Partners/Customers`
  - **Use existing lots:** activado
  - **Show operations:** desactivado

## Requisitos

- Depende únicamente del módulo `stock`.

## Instalación

1. Copiar o clonar el directorio `sng_warehouse_retc` dentro de una ruta incluida en `addons_path` (por ejemplo, `/opt/odoo18/odoo18-custom-addons/`).
2. Reiniciar el servidor de Odoo.
3. Actualizar la lista de aplicaciones.
4. Instalar el módulo **RETC automático por almacén**.

## Notas

- Si el tipo RETC ya existe para el almacén, no se vuelve a crear.
- El módulo no modifica ni elimina tipos de operación existentes como `RELL`.
- Para almacenes creados antes de instalar este módulo, se puede seguir usando el script `scripts/create_retc_picking_type.py`.
