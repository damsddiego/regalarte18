# sng_stock_picking_stages — Stock Picking Stages

Módulo para Odoo 18 que agrega etapas personalizables al flujo de trabajo de transferencias de inventario (`stock.picking`).

Inspirado en `eg_sales_order_stages`, extiende el mismo concepto al módulo de inventario con soporte adicional para filtrar etapas por tipo de operación.

## Descripción

Agrega un campo de **etapa** independiente al modelo `stock.picking`, permitiendo a los equipos de almacén gestionar su flujo de trabajo interno sin alterar el estado nativo de Odoo (`draft`, `waiting`, `confirmed`, `assigned`, `done`, `cancel`).

## Funcionalidades

### Modelo `stock.picking.stage`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | Char | Nombre de la etapa (requerido, traducible) |
| `sequence` | Integer | Orden de aparición (default: 10) |
| `fold` | Boolean | Colapsar columna en Kanban |
| `show_in_kanban` | Boolean | Mostrar como columna en Kanban (default: True) |
| `picking_type_code` | Selection | Limitar la etapa a un tipo de operación (`incoming`, `outgoing`, `internal`). Vacío = aplica a todos |

Las etapas se ordenan por `sequence, id`.

### Extensión de `stock.picking`

Campo `stage_id` (Many2one → `stock.picking.stage`) agregado a cada transferencia:

- **Valor por defecto:** primera etapa disponible con `show_in_kanban = True`, filtrando opcionalmente por `picking_type_code` del contexto.
- **Tracking:** los cambios de etapa quedan registrados en el chatter.
- **`copy=False`:** al duplicar una transferencia, la etapa no se copia (comienza desde el default).
- **Kanban expand:** solo columnas con `show_in_kanban = True`.

### Vistas modificadas

| Vista | Cambio |
|-------|--------|
| Formulario de transferencia | Barra de estado clickeable (`statusbar`) con las etapas, debajo del header nativo |
| Lista de transferencias | Columna `Stage` opcional (visible por defecto) junto al campo `state` |
| Búsqueda / filtros | Opción de agrupar por etapa en el panel de filtros |

### Menú de configuración

Accesible desde **Inventario → Configuración → Picking Stages**. Permite crear, reordenar (drag & drop por `sequence`) y configurar etapas con su tipo de operación asociado.

## Permisos

| Grupo | Lectura | Escritura | Creación | Eliminación |
|-------|---------|-----------|----------|-------------|
| `stock.group_stock_user` (Operador) | ✓ | — | — | — |
| `stock.group_stock_manager` (Gerente) | ✓ | ✓ | ✓ | ✓ |

A diferencia de `eg_sales_order_stages`, la administración de etapas está restringida a gerentes de inventario.

## Estructura de archivos

```
sng_stock_picking_stages/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── stock_picking_stage.py   # Modelo stock.picking.stage
│   └── stock_picking.py         # Herencia de stock.picking
├── views/
│   ├── stock_picking_stage_view.xml   # CRUD de etapas + menú de config
│   └── stock_picking_view.xml         # Inyección en vistas de transferencias
└── security/
    └── ir.model.access.csv
```

## Dependencias

- `stock` (módulo estándar de Odoo)

## Diferencias respecto a `eg_sales_order_stages`

| Aspecto | `eg_sales_order_stages` | `sng_stock_picking_stages` |
|---------|------------------------|---------------------------|
| Modelo extendido | `sale.order` | `stock.picking` |
| Depende de | `sale_management` | `stock` |
| Filtro por tipo | No aplica | `picking_type_code` (opcional) |
| Permisos | Todos los usuarios | Por grupo (operador / gerente) |
| `copy` del campo | — | `False` (no se copia al duplicar) |
| Default inteligente | Primera etapa global | Primera etapa filtrando por tipo de operación del contexto |

## Instalación

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf -i sng_stock_picking_stages -d RegalarteProd --stop-after-init
```

## Actualización

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf -u sng_stock_picking_stages -d RegalarteProd --stop-after-init
```

## Notas de uso

- Las etapas son **independientes** del estado técnico de Odoo. Una transferencia puede estar en estado `done` y en cualquier etapa del pipeline personalizado.
- Para tener etapas distintas por tipo de operación, configurar el campo **Operation Type** en cada etapa. Las etapas sin tipo asignado aparecen en todos los tipos.
- El campo `fold` está disponible en la vista de configuración; permite colapsar la columna en la vista Kanban de Odoo si se habilita.
