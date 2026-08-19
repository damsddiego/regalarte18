# Reporte CxC por Cliente (`sng_customer_ar_report`)

**Versión:** 18.0.1.0.0  
**Autor:** SNG  
**Licencia:** LGPL-3  
**Categoría:** Contabilidad

---

## Descripción General

`sng_customer_ar_report` es un módulo de **análisis de Cuentas por Cobrar (CxC)** que genera una vista consolidada por cliente con:

- **Total Facturado** — Suma de todas las facturas de cliente confirmadas.
- **Total Pendiente** — Saldo residual pendiente de cobro.
- **Días Promedio de Pago** — Promedio de días que tarda el cliente en pagar sus facturas (calculado solo sobre facturas ya completamente pagadas).
- **Conteo de facturas** — Total de facturas y cuántas han sido pagadas.

El reporte está basado en una **SQL VIEW** (no hay datos almacenados), lo que garantiza máxima eficiencia y datos siempre en tiempo real. Soporta entornos **multi-compañía** y permite exportación a Excel.

---

## Módulos Requeridos

| Módulo | Descripción |
|---|---|
| `account` | Módulo contable base de Odoo (facturas, pagos, conciliaciones) |
| `customer_sequence` | Proporciona el campo `unique_id` en `res.partner` para el código de cliente |

---

## Funcionalidades

### Vista Lista (List)
Muestra una fila por cada combinación `(cliente, compañía)` con columnas:

| Columna | Descripción |
|---|---|
| Código - Cliente | `unique_id` + nombre del contacto |
| Cliente | Enlace al `res.partner` |
| Plazo de Crédito | Término de pago asignado al cliente |
| Compañía | Visible solo en entornos multi-compañía |
| # Facturas | Total de facturas confirmadas |
| # Pagadas | Facturas con saldo = 0 |
| Total Facturado | Suma de `amount_total_signed` con subtotal de columna |
| Total Pendiente | Suma de `amount_residual_signed` con subtotal de columna |
| Días Promedio de Pago | Promedio de días entre fecha de factura y fecha de último pago |

### Vista Pivot
Permite análisis dimensional agrupando por cliente con medidas:
- Total Facturado
- Total Pendiente
- Días Promedio de Pago

### Filtros de Búsqueda Rápida
| Filtro | Descripción |
|---|---|
| Este Mes | Facturas del mes en curso |
| Mes Pasado | Facturas del mes anterior |
| Este Año | Facturas del año en curso |
| Solo con Saldo | Clientes con `amount_due > 0` |

### Agrupaciones disponibles
- Por Cliente
- Por Compañía *(solo en multi-compañía)*

### Wizard de Filtros
Formulario de diálogo para aplicar filtros antes de abrir el reporte:
- Rango de fechas (Desde / Hasta)
- Compañía
- Cliente específico
- Toggle "Solo con saldo pendiente"

---

## SQL VIEW — Diseño Técnico

El modelo `customer.ar.report` no almacena datos (`_auto = False`). La vista SQL se define en `_table_query` y ejecuta la siguiente lógica:

```sql
SELECT
    MIN(am.id)                    AS id,              -- ID estable por fila
    am.partner_id,
    CONCAT(rp.unique_id, ' - ', rp.name) AS partner_code,
    am.company_id,
    rc.currency_id,
    SUM(am.amount_total_signed)   AS amount_invoiced,  -- Total facturado
    SUM(am.amount_residual_signed) AS amount_due,       -- Saldo pendiente
    COUNT(am.id)                  AS invoice_count,
    COUNT(am.id) FILTER (WHERE am.amount_residual = 0) AS paid_invoice_count,
    MIN(am.invoice_date)          AS invoice_date_min,
    MAX(am.invoice_date)          AS invoice_date_max,
    AVG(                                               -- Días promedio de pago
        CASE
            WHEN am.amount_residual = 0
                 AND pay_dates.last_payment_date IS NOT NULL
            THEN (pay_dates.last_payment_date - am.invoice_date)
            ELSE NULL
        END
    )                             AS avg_days_to_pay

FROM account_move am
JOIN res_company rc ON rc.id = am.company_id
JOIN res_partner rp ON rp.id = am.partner_id

-- Subconsulta LATERAL: última fecha de pago por factura (solo facturas pagadas)
LEFT JOIN LATERAL (
    SELECT MAX(apr.max_date) AS last_payment_date
    FROM account_partial_reconcile apr
    JOIN account_move_line aml_inv ON aml_inv.id = apr.debit_move_id
    JOIN account_account aa ON aa.id = aml_inv.account_id
    WHERE aml_inv.move_id = am.id
      AND aa.account_type = 'asset_receivable'
) pay_dates ON am.amount_residual = 0

WHERE am.move_type = 'out_invoice'
  AND am.state = 'posted'

GROUP BY am.partner_id, rp.unique_id, rp.name, am.company_id, rc.currency_id
```

**Decisiones de diseño importantes:**
- `amount_total_signed` y `amount_residual_signed` incluyen el signo de la moneda de la compañía → correcto para entornos **multi-moneda/multi-compañía**.
- `avg_days_to_pay` se calcula **solo sobre facturas 100% pagadas** (`amount_residual = 0`) y usa `MAX(apr.max_date)` como la fecha del último pago de conciliación.
- `invoice_date_min` / `invoice_date_max` no están en el `GROUP BY`; se exponen como campos de fecha mínima/máxima del grupo para permitir filtros de rango de fecha en el dominio.
- Los clientes sin facturas pagadas mostrarán `avg_days_to_pay = NULL` (presentado como `0.00` en la UI).

---

## Acceso y Menú

El reporte se encuentra en:

```
Contabilidad → Informes → CxC por Cliente
Contabilidad → Informes → CxC por Cliente (Filtro)   ← vía Wizard
```

---

## Instalación

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf \
    -i sng_customer_ar_report \
    -d RegalarteProd \
    --stop-after-init
```

Actualización tras cambios:

```bash
python odoo18/odoo-bin -c /etc/odoo18.conf \
    -u sng_customer_ar_report \
    -d RegalarteProd \
    --stop-after-init
```

---

## Estructura del Módulo

```
sng_customer_ar_report/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── sng_customer_ar_report.py     # Modelo SQL VIEW (customer.ar.report)
├── views/
│   ├── sng_customer_ar_report_views.xml         # List, Pivot, Search, Action, Menú
│   └── sng_customer_ar_report_wizard_views.xml  # Wizard form, Action, Menú
├── wizard/
│   ├── __init__.py
│   └── sng_customer_ar_report_wizard.py         # Modelo del wizard
└── security/
    └── ir.model.access.csv
```

---

## Seguridad (Permisos)

| Regla de acceso | Modelo | Grupo | R | W | C | D |
|---|---|---|---|---|---|---|
| `customer.ar.report.invoice` | `customer.ar.report` | Facturación | ✓ | ✗ | ✗ | ✗ |
| `customer.ar.report.user` | `customer.ar.report` | Contabilidad | ✓ | ✗ | ✗ | ✗ |
| `customer.ar.report.wizard.invoice` | `customer.ar.report.wizard` | Facturación | ✓ | ✓ | ✓ | ✓ |
| `customer.ar.report.wizard.user` | `customer.ar.report.wizard` | Contabilidad | ✓ | ✓ | ✓ | ✓ |

> El reporte principal es de **solo lectura** para todos los grupos (es una SQL VIEW). El wizard sí requiere crear/modificar registros transitorios.

---

## Notas

- Al ser una SQL VIEW, el modelo **no puede ser editado ni eliminado** desde la interfaz (vistas con `create="false" edit="false" delete="false"`).
- La exportación a Excel usa el botón estándar de exportación de Odoo en la vista lista.
- El campo `company_id` en el wizard usa como valor por defecto la compañía activa del usuario (`env.company`).
