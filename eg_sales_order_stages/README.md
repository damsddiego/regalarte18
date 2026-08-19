# eg_sales_order_stages — Sales Order Stages

Módulo para Odoo 18 que agrega etapas personalizables al flujo de trabajo de órdenes de venta.

## Descripción

Este módulo extiende el modelo `sale.order` con un campo de **etapa** independiente del estado nativo de Odoo (`draft`, `sale`, `done`, etc.). Permite a los equipos de ventas definir y gestionar su propio flujo de trabajo interno sin alterar la lógica estándar de Odoo.

## Funcionalidades

### Modelo `sale.order.stage`

Nuevo modelo que representa cada etapa del pipeline de ventas. Campos:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | Char | Nombre de la etapa (requerido) |
| `sequence` | Integer | Orden de aparición (default: 10) |
| `fold` | Boolean | Colapsar columna en vista Kanban |
| `show_in_kanban` | Boolean | Mostrar la etapa como columna en Kanban (default: True) |

Las etapas se ordenan por `sequence, id`.

### Extensión de `sale.order`

Se agrega el campo `sale_order_stages` (Many2one → `sale.order.stage`) a cada orden de venta:

- **Valor por defecto:** primera etapa disponible (orden por `sequence, id`).
- **Tracking:** los cambios de etapa quedan registrados en el chatter.
- **Kanban expand:** solo se muestran como columnas las etapas con `show_in_kanban = True`.

### Vistas modificadas

| Vista | Cambio |
|-------|--------|
| Formulario de orden de venta | Barra de estado clickeable (`statusbar`) con las etapas, insertada debajo del header nativo |
| Lista de órdenes de venta | Columna `Stage` opcional (visible por defecto) junto al campo `state` |
| Gráfico de órdenes de venta | Agrupación disponible por etapa |
| Búsqueda / filtros | Opción de agrupar por etapa en el panel de filtros |

### Menú de configuración

Accesible desde **Ventas → Configuración → Sale Stages**. Permite crear, reordenar (drag & drop por `sequence`) y configurar etapas.

## Estructura de archivos

```
eg_sales_order_stages/
├── __manifest__.py
├── models/
│   ├── sale_order_stage.py     # Modelo sale.order.stage
│   └── sale_order.py           # Herencia de sale.order
├── views/
│   ├── sale_order_stage_view.xml   # CRUD de etapas + menú de config
│   └── sale_order_view.xml         # Inyección en vistas de órdenes
├── security/
│   └── ir.model.access.csv     # Acceso total al modelo sale.order.stage para todos los usuarios
└── i18n/
    └── es.po                   # Traducciones al español
```

## Dependencias

- `sale_management` (módulo estándar de Odoo)

## Permisos

El CSV de acceso otorga permisos de lectura, escritura, creación y eliminación sobre `sale.order.stage` sin restricción de grupo (acceso para todos los usuarios internos).

## Instalación

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf -i eg_sales_order_stages -d RegalarteProd --stop-after-init
```

## Actualización

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf -u eg_sales_order_stages -d RegalarteProd --stop-after-init
```

## Notas de implementación

- Las etapas son **independientes** del estado técnico de Odoo (`state`). Una orden puede estar en estado `sale` (confirmada) y en cualquier etapa del pipeline personalizado.
- El campo `fold` existe en el modelo pero no se expone en la vista de configuración; puede habilitarse si se requiere colapsar columnas en Kanban.
- Autor original: INKERP. Licencia: OPL-1. Adaptado para uso interno en SNG/Regalarte.
