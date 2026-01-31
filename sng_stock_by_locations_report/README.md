# SNG Stock By Customer Location Report

## Descripción

Este módulo permite generar reportes de inventario agrupados por cliente, mostrando el valor total del stock almacenado en ubicaciones de tipo "customer" asociadas a cada cliente.

## Características

- **Reporte por cliente**: Muestra el stock agrupado por cliente (res.partner)
- **Múltiples formatos**: XLSX, PDF y vista en pantalla
- **Métricas incluidas**:
  - Unique ID del cliente
  - Nombre completo del cliente
  - Ubicación asociada
  - Cantidad total de productos
  - Valor total (basado en precio de venta)
- **Filtros disponibles**:
  - Todos los clientes o clientes específicos
  - Filtro por compañías
  - Filtro por rango de fechas

## Instalación

1. Copiar el módulo a la carpeta de addons de Odoo
2. Actualizar la lista de módulos: `Settings > Apps > Update Apps List`
3. Buscar "SNG Stock By Customer Location"
4. Hacer clic en "Install"

## Configuración Inicial

**IMPORTANTE**: Antes de usar el reporte, debes configurar las ubicaciones de cliente:

1. Ir a `Inventory > Configuration > Locations`
2. Para cada ubicación de tipo "Customer Location":
   - Abrir la ubicación
   - En el campo **"Associated Customer"** seleccionar el cliente correspondiente
   - Guardar

Sin este paso, el reporte no mostrará datos porque no podrá asociar las ubicaciones con los clientes.

## Uso

1. Ir a `Inventory > Reporting > Stock By Customer Location`
2. Seleccionar el formato de reporte (XLSX o PDF)
3. Elegir entre todos los clientes o clientes específicos
4. Seleccionar las compañías (opcional)
5. Definir el rango de fechas (opcional)
6. Hacer clic en "Generate Report"

## Requisitos

- Odoo 18.0
- Módulos base instalados: `stock`, `product`, `sale_management`
- Las ubicaciones de clientes deben ser de tipo "customer"
- Las ubicaciones deben tener el campo `partner_id` configurado

## Consideraciones Técnicas

### Query SQL
El módulo utiliza una consulta SQL optimizada que:
- Busca en `stock_quant` las cantidades actuales
- Filtra por ubicaciones tipo 'customer'
- Agrupa por cliente y ubicación
- Calcula el valor total usando `quantity * list_price`

### Cálculo de Valor
El valor total se calcula multiplicando:
- **Cantidad**: La cantidad disponible en `stock_quant`
- **Precio**: El precio de venta (`list_price`) del producto

### Limitaciones
- El reporte muestra el stock **actual**, no histórico
- Solo considera ubicaciones tipo 'customer' con partner_id asignado
- Los productos deben tener un precio de venta configurado

## Estructura del Módulo

```
sng_stock_by_locations_report/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── main.py
├── models/
│   ├── __init__.py
│   └── stock_location.py              # Extiende stock.location con partner_id
├── report/
│   ├── __init__.py
│   ├── sng_stock_customer_report.py
│   ├── sng_stock_customer_report.xml
│   └── sng_stock_customer_report_templates.xml
├── security/
│   └── ir.model.access.csv
├── static/
│   └── src/
│       └── js/
│           └── action_manager.js
├── views/
│   └── stock_location_views.xml       # Vista para asignar partner_id
└── wizard/
    ├── __init__.py
    ├── sng_stock_customer_report.py
    └── sng_stock_customer_report_views.xml
```

## Autor

**SNG Solutions**

## Licencia

LGPL-3
