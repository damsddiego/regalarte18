==================
Stock by Customer
==================

Este módulo proporciona un reporte que muestra el valor total de inventario
para cada cliente que tiene una ubicación de venta asignada.

Características
===============

* Lista todos los clientes con ubicaciones de venta asignadas (sale_location_id)
* Calcula el valor total del inventario por ubicación de cliente
* Incluye ubicaciones hijas en los cálculos
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

Uso
===

1. Ir a **Inventario > Stock by Customer > Stock by Customer Report**
2. Seleccionar los filtros deseados:

   - **Compañía**: La compañía para la cual generar el reporte
   - **Fecha del Reporte**: Fecha para calcular el valor del inventario
   - **Incluir Clientes con Stock Cero**: Si debe incluir clientes sin inventario

3. Click en "Generar Reporte"
4. Click en "Descargar" para obtener el archivo Excel

Cálculo del Valor
=================

El valor del inventario se calcula como:

**Valor Total = Σ (Cantidad × Precio de Venta)**

Para cada producto en la ubicación del cliente y sus ubicaciones hijas.

Estructura del Reporte
======================

Hoja de Resumen
---------------

* Código Cliente
* Nombre Cliente
* Ubicación
* Cantidad de Productos
* Cantidad Total
* Valor Total

Hoja de Detalle
---------------

* Código Cliente
* Nombre Cliente
* Código Producto
* Producto
* Cantidad
* Unidad de Medida
* Precio Unitario (Precio de Venta)
* Valor Total
* Ubicación específica

Autor
=====

SNG

Licencia
========

LGPL-3
