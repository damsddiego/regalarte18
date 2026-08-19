# SNG Sales Commission

## Objetivo

Este módulo permite liquidar comisiones de vendedores en Odoo usando esta lógica:

- El vendedor es un contacto `res.partner`.
- La comisión nace por cobros conciliados de facturas de cliente.
- La base se calcula sobre el monto cobrado sin IVA.
- El porcentaje base depende del bucket de antigüedad al momento del cobro.
- El monto mensual final se ajusta por cumplimiento de meta.

## Dependencias

El módulo depende de:

- `account`
- `sale`
- `sales_commission_omax`

## Conceptos Clave

### 1. Vendedor

El vendedor no es un usuario de ventas estándar de Odoo. En este módulo el vendedor es un contacto:

- En el contacto del vendedor marque `Is Salesperson`.
- En cada cliente asigne `Assigned Salesperson`.

Cuando una factura se emite para ese cliente, la liquidación toma ese contacto como vendedor.

### 2. Plan de Comisión

El plan define:

- Compañía
- Vigencia desde una fecha inicial, con fecha final opcional
- Moneda de liquidación
- Buckets de antigüedad
- Tabla de cumplimiento

Solo debe existir un plan activo con vigencia traslapada por compañía. Si deja la fecha final vacía, el plan queda vigente para todos los meses futuros hasta que active un plan nuevo.

### 3. Meta Mensual

La meta se registra manualmente por:

- Plan
- Vendedor
- Año
- Mes

### 4. Liquidación

La liquidación es el cierre mensual por vendedor y periodo. Guarda:

- Meta
- Venta real sin IVA
- % de cumplimiento
- Factor aplicado
- Comisión bruta
- Comisión final
- Detalle por pago aplicado

## Instalación

1. Instale el módulo `sng_sales_commission`.
2. Verifique que `sales_commission_omax` ya esté instalado.
3. Confirme que existan:
   - diarios bancarios
   - métodos de pago de entrada
   - cuentas contables de clientes

## Configuración Inicial

### Paso 1. Crear vendedores

En **Contactos**:

1. Abra el contacto que será vendedor.
2. Marque `Is Salesperson`.

### Paso 2. Asignar vendedor a clientes

En cada cliente:

1. Abra el contacto.
2. Seleccione `Assigned Salesperson`.

Este valor es el que luego usa la liquidación para agrupar comisiones.

### Paso 3. Crear el plan

Ruta:

- **Ventas > Comisiones > Configuración > Planes**

Complete:

- `Nombre`
- `Compañía`
- `Moneda de liquidación`
- `Fecha inicio`
- `Fecha fin` (opcional)

Si el plan debe seguir aplicando mes a mes, deje `Fecha fin` vacío. Cuando active un plan nuevo con una fecha de inicio posterior, el sistema cerrará el plan activo anterior el día previo.

#### Buckets de antigüedad

En la pestaña de buckets configure al menos:

- un bucket `No vencido`
- los buckets vencidos por rango de días

Ejemplo basado en el Excel:

- `No vencido` -> `2.00`
- `1-45 días` -> `1.50`
- `46-60 días` -> `1.00`
- `61-90 días` -> `0.50`
- `91+ días` -> `0.00`

Notas:

- `No vencido` aplica cuando la fecha de pago/conciliación es menor o igual a la fecha de vencimiento.
- Los buckets vencidos no pueden traslaparse.

#### Tabla de cumplimiento

En la pestaña de cumplimiento configure los rangos de porcentaje y su factor de pago.

Ejemplo:

- `110` a `119.9999` -> `1.15`
- `100` a `109.9999` -> `1.00`
- `95` a `99.9999` -> `0.95`
- `70` a `94.9999` -> `0.50`
- `0` a `69.9999` -> `0.00`

Notas:

- Los rangos no pueden traslaparse.
- El factor multiplica la comisión bruta del mes.

### Paso 4. Activar el plan

En el plan use el botón `Activar`.

## Registro de Metas

Ruta:

- **Ventas > Comisiones > Configuración > Metas**

Para cada vendedor cree una meta con:

- `Plan`
- `Vendedor`
- `Año`
- `Mes`
- `Meta`

Debe existir una meta por vendedor por mes si se desea calcular correctamente el factor por cumplimiento.

## Flujo Operativo

### 1. Emitir facturas

Trabaje normalmente con facturas de cliente (`out_invoice`).

Importante:

- La factura debe quedar `posted`.
- La factura debe tener vendedor derivado del cliente o uno ya definido.

### 2. Registrar cobros

Registre pagos normalmente y concilie la factura total o parcialmente.

El módulo toma cada `account.partial.reconcile` del periodo para generar el detalle de comisión.

### 3. Generar liquidaciones

Ruta:

- **Ventas > Comisiones > Operaciones > Generar liquidaciones**

Seleccione:

- `Plan`
- `Año`
- `Mes`
- uno o varios vendedores

Luego presione `Generar`.

El sistema:

1. Busca cobros conciliados del periodo.
2. Identifica la factura y el vendedor.
3. Calcula días vencidos al momento del cobro.
4. Busca el bucket de antigüedad aplicable.
5. Calcula monto cobrado sin IVA.
6. Convierte a moneda compañía si aplica.
7. Suma la venta real del mes sin IVA.
8. Calcula `% cumplimiento = venta real / meta`.
9. Busca la regla de cumplimiento.
10. Calcula comisión bruta y comisión final.

### 4. Revisar la liquidación

Ruta:

- **Ventas > Comisiones > Operaciones > Liquidaciones**

Revise:

- `Meta`
- `Venta real sin IVA`
- `% cumplimiento`
- `Factor aplicado`
- `Comisión bruta`
- `Comisión final`

En la pestaña `Detalle` verá por línea:

- fecha de aplicación
- factura
- pago
- cliente
- bucket
- monto aplicado sin IVA
- comisión base
- comisión final

### 5. Aprobar y cerrar

Una vez revisada:

1. Presione `Aprobar`.
2. Cuando el cierre esté confirmado, presione `Cerrar`.

Restricción:

- una liquidación `approved` o `closed` no se recalcula.

## Campo "Requiere recálculo"

Si una liquidación en borrador muestra `Requiere recálculo`, significa que hubo cambios posteriores en conciliaciones del periodo.

En ese caso:

1. Abra la liquidación.
2. Presione `Generar` nuevamente.

## Cómo Calcula el Sistema

### Base de Comisión

La base de comisión por línea es:

- monto aplicado del cobro
- proporcional al monto sin IVA de la factura

### Antigüedad

Se calcula como:

- `fecha_aplicación_pago - fecha_vencimiento_factura`

Regla:

- si el resultado es `<= 0`, cae en `No vencido`
- si es `> 0`, cae en el rango vencido correspondiente

### Cumplimiento

La venta real del mes se calcula con:

- facturas de cliente publicadas del periodo
- del vendedor
- usando `amount_untaxed_signed`

La fórmula es:

- `% cumplimiento = venta_real_sin_iva / meta * 100`

### Comisión Final

La fórmula es:

- `comisión base = monto aplicado sin IVA * % bucket / 100`
- `comisión final = comisión base * factor de cumplimiento`

## Moneda

Si la factura está en moneda distinta a la moneda de la compañía:

- el sistema conserva el monto original
- convierte el monto base a moneda compañía en la fecha de aplicación del pago

## Recomendaciones de Uso

- Mantenga un solo plan activo por vigencia y compañía; deje la fecha final vacía para que siga aplicando a meses futuros.
- Cree las metas antes de generar liquidaciones del mes.
- No cierre la liquidación hasta confirmar que no faltan cobros conciliados.
- Revise siempre las líneas con bucket `No vencido` y los vencidos de mayor antigüedad.

## Limitaciones de la V1

- No genera factura de proveedor ni asiento contable automático.
- No importa metas desde Excel.
- El cierre es interno y de reporte.

## Rutas Principales del Módulo

- Modelo del plan: `models/commission_plan.py`
- Modelo de liquidación: `models/commission_settlement.py`
- Wizard de generación: `wizard/commission_generate_wizard.py`
- Vistas operativas: `views/commission_settlement_views.xml`
- Reporte PDF: `report/commission_report.xml`
