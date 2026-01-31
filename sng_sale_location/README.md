# Sale Order Location Selection Module

## Descripción
Módulo para Odoo 18 que permite seleccionar una ubicación interna específica al crear órdenes de venta, con validación de stock y control de reservas.

## Características

### ✅ Selección de Ubicación
- Campo `Ubicación de Origen` en la orden de venta
- Solo muestra ubicaciones internas activas
- Compatible con multi-empresa
- Se establece ANTES de confirmar la orden

### ✅ Validación de Stock
- Valida disponibilidad de stock en la ubicación seleccionada
- Bloquea completamente la confirmación si no hay stock suficiente
- Mensajes de error claros indicando productos y cantidades faltantes

### ✅ Control de Reservas
- Las reservas se realizan EXCLUSIVAMENTE desde la ubicación seleccionada
- No permite reservas parciales desde otras ubicaciones
- La ubicación se propaga automáticamente a pickings y movimientos de stock

### ✅ Seguridad
- Acceso para todos los usuarios de ventas
- Permisos configurables por grupo

## Instalación

1. Copiar el módulo a la carpeta de addons de Odoo
2. Actualizar lista de aplicaciones
3. Instalar el módulo "Sale Order Location Selection"

## Uso

### Crear Orden de Venta con Ubicación

1. Crear nueva orden de venta
2. Agregar líneas de pedido
3. **Seleccionar ubicación de origen** (campo obligatorio)
4. Confirmar orden

### Validación Automática

Al confirmar la orden, el sistema:
- Verifica stock disponible en la ubicación seleccionada
- Si hay stock suficiente → Confirma y crea picking
- Si NO hay stock suficiente → Bloquea con mensaje de error

### Ejemplo de Error

```
Stock insuficiente en la ubicación seleccionada:

• [PROD001] Producto A: Requerido 10.00, Disponible 5.00 en WH/Stock/Shelf 1
• [PROD002] Producto B: Requerido 20.00, Disponible 0.00 en WH/Stock/Shelf 1

Por favor, seleccione otra ubicación o ajuste las cantidades.
```

## Consideraciones Técnicas

### Flujo de Datos
```
Sale Order (location_id) 
    → Stock Picking (sale_location_id) 
        → Stock Moves (location_id)
            → Reservations (quants filtered by location)
```

### Ubicaciones Filtradas
- `usage = 'internal'` (solo internas)
- `company_id` = empresa de la orden o sin empresa
- `active = True`

### NO Rompe Flujo Estándar
- Usa herencia de modelos
- Contextos para pasar datos
- Hooks oficiales de Odoo
- No hardcodea IDs

### Escalabilidad
- Compatible con múltiples empresas
- Funciona con múltiples almacenes
- No afecta rendimiento en órdenes grandes

## Campos Agregados

### sale.order
- `location_id` (Many2one → stock.location)

### stock.picking
- `sale_location_id` (Many2one → stock.location, readonly)

## Métodos Sobrescritos

### sale.order
- `action_confirm()` - Validación de stock
- `_prepare_procurement_group_vals()` - Propagación de contexto

### stock.picking
- `create()` - Captura ubicación del contexto
- `_action_confirm()` - Actualiza ubicación en movimientos

### stock.move
- `_action_assign()` - Fuerza reserva desde ubicación específica
- `_update_reserved_quantity()` - Bloquea reservas de otras ubicaciones
- `_get_available_quantity()` - Filtra cantidad disponible por ubicación

## Soporte
Módulo desarrollado por SNG para Odoo 18

## Licencia
LGPL-3
