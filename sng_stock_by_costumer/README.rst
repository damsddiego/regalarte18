==================
Stock by Customer
==================

Este módulo proporciona un reporte interactivo para analizar el inventario
asociado a clientes que tienen una ubicación de venta asignada en
`res.partner.sale_location_id`.

Características
===============

* Lista todos los clientes con ubicaciones de venta asignadas (sale_location_id)
* Calcula stock por cliente, producto y ubicación interna
* Incluye ubicaciones hijas en los cálculos
* Permite analizar resultados en vistas nativas de Odoo: lista, pivot, gráfico y formulario
* Permite filtrar y agrupar por cliente, vendedor, ubicación, producto, fecha y compañía
* Incluye acceso directo desde el formulario del contacto
* Exporta el reporte a formato Excel con dos hojas:

  - **Resumen**: Vista consolidada por cliente con totales
  - **Detalle por Producto**: Vista detallada producto por producto

Instalación
===========

1. Copiar el módulo a la carpeta de addons de Odoo
2. Actualizar la lista de módulos
3. Instalar el módulo "Stock by Customer"

Dependencias
============

* base
* stock
* stock_account
* sale_stock_sng
* sales_commission_omax
* customer_sequence

Uso
===

Opción 1: Desde Inventario
--------------------------

1. Ir a **Inventario > Stock by Customer > Stock by Customer Report**
2. Seleccionar los filtros deseados:

   - **Compañía**: La compañía para la cual generar el reporte
   - **Fecha del Reporte**: Fecha para calcular el stock
   - **Incluir Clientes con Stock Cero**: Si debe incluir clientes sin inventario
   - **Clientes**: Restringe a clientes específicos
   - **Vendedores**: Restringe por `assigned_salesperson_id`
   - **Ubicaciones**: Restringe por `sale_location_id`
   - **Productos**: Restringe a productos específicos

3. Click en "Generar Reporte"
4. Analizar el resultado en pantalla usando filtros, agrupaciones, pivot o gráfico
5. Click en "Descargar Excel" para obtener el archivo formateado

Opción 2: Desde Contactos
-------------------------

1. Abrir un contacto o cliente
2. Verificar que tenga una **Ubicación de venta** en `sale_location_id`
3. Click en el botón **Stock por Cliente**
4. El sistema abre el mismo reporte ya filtrado por la ubicación asignada a ese cliente

Cálculo del Valor
=================

El valor del reporte se calcula como:

* **Subtotal = Σ (Cantidad × Precio de Venta)**
* **Impuesto = cálculo de impuestos de venta del producto**
* **Total = Subtotal + Impuesto**

Para cada producto en la ubicación del cliente y sus ubicaciones hijas.
La cantidad se calcula a la fecha seleccionada.

Estructura del Reporte
======================

Hoja de Resumen
---------------

* Código Cliente
* Nombre Cliente
* Ubicación
* Cantidad de Productos
* Cantidad Total
* Subtotal
* Impuesto
* Total

Hoja de Detalle
---------------

* Código Cliente
* Nombre Cliente
* Vendedor
* Código Producto
* Producto
* Cantidad
* Unidad de Medida
* Precio de Venta
* Subtotal
* Impuesto
* Total
* Ubicación específica

Vista Analítica en Odoo
=======================

El resultado en pantalla se genera sobre líneas del modelo transitorio
`stock.by.customer.wizard.line`, lo que permite usar:

* búsqueda por cliente, vendedor, ubicación y producto
* filtros rápidos para líneas con stock o sin stock
* agrupaciones por cliente, vendedor, ubicación, producto, fecha y compañía
* vista pivot para análisis agregado
* vista gráfica para análisis visual

Notas Técnicas
==============

* El reporte toma como ubicación raíz del cliente el campo `sale_location_id`
* Solo considera ubicaciones internas (`usage = internal`)
* Si la fecha del reporte es anterior al momento actual, el stock se reconstruye revirtiendo movimientos posteriores ya realizados
* El archivo Excel conserva una hoja de resumen y otra de detalle
* El botón del contacto usa `commercial_partner_id` para soportar contactos hijos

Limitaciones
============

* Es un reporte transitorio orientado a análisis en pantalla y exportación
* El precio utilizado es el `list_price` del producto en la compañía seleccionada
* Si un contacto no tiene `sale_location_id`, el botón contextual no puede abrir el reporte

Autor
=====

SNG

Licencia
========

LGPL-3
