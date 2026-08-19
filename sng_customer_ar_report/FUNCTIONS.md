# Referencia Funcional — `sng_customer_ar_report`

Documentación técnica de todas las clases, campos y métodos del módulo.

---

## `models/sng_customer_ar_report.py` — `CustomerArReport`

**Modelo:** `customer.ar.report`  
**Tipo:** `_auto = False` (SQL VIEW — no almacena datos propios)  
**Orden por defecto:** `amount_due desc`  
**Nombre de registro:** `partner_id`

### Campos

| Campo | Tipo | Descripción |
|---|---|---|
| `partner_id` | `Many2one(res.partner)` | Cliente al que pertenece la fila. |
| `partner_code` | `Char` | Concatenación de `unique_id` + `' - '` + `name` del contacto (desde SQL). |
| `company_id` | `Many2one(res.company)` | Compañía de las facturas agrupadas. |
| `currency_id` | `Many2one(res.currency)` | Moneda de la compañía (tomada de `res_company.currency_id`). |
| `payment_term_id` | `Many2one(account.payment.term)` | Plazo de crédito del cliente (campo **relacionado** desde `partner_id.property_payment_term_id`; no viene del SQL). |
| `amount_invoiced` | `Monetary` | Suma de `amount_total_signed` de todas las facturas confirmadas del grupo. |
| `amount_due` | `Monetary` | Suma de `amount_residual_signed` de todas las facturas del grupo (saldo pendiente). |
| `avg_days_to_pay` | `Float(16,2)` | Días promedio entre `invoice_date` y la fecha del último pago (solo facturas 100% pagadas). Agrupador: `avg`. |
| `invoice_count` | `Integer` | Número total de facturas confirmadas del grupo. |
| `paid_invoice_count` | `Integer` | Número de facturas con `amount_residual = 0` (completamente pagadas). |
| `invoice_date_min` | `Date` | Fecha de la factura más antigua del grupo (usada para filtros de rango). |
| `invoice_date_max` | `Date` | Fecha de la factura más reciente del grupo (usada para filtros de rango). |

### Propiedad

#### `_table_query` → `SQL`
- Define la consulta SQL que construye la vista en base de datos.
- **Fuentes de datos:**
  - `account_move` (`am`) — Facturas de cliente (`move_type = 'out_invoice'`, `state = 'posted'`).
  - `res_company` (`rc`) — Para obtener `currency_id`.
  - `res_partner` (`rp`) — Para obtener `unique_id` y `name`.
  - **Subconsulta LATERAL** (`pay_dates`) — Para calcular la última fecha de pago por factura:
    - Une `account_partial_reconcile` → `account_move_line` → `account_account`.
    - Filtra líneas de tipo `asset_receivable`.
    - Solo se activa (`LEFT JOIN ... ON am.amount_residual = 0`) para facturas ya pagadas.
- **Agrupamiento:** `(am.partner_id, rp.unique_id, rp.name, am.company_id, rc.currency_id)`.
- **`id` de la fila:** `MIN(am.id)` — Garantiza un ID estable y único por grupo (partner + compañía).

**Lógica de `avg_days_to_pay`:**
```sql
AVG(
    CASE
        WHEN am.amount_residual = 0
             AND pay_dates.last_payment_date IS NOT NULL
        THEN (pay_dates.last_payment_date - am.invoice_date)
        ELSE NULL   -- excluye facturas sin pagar del promedio
    END
)
```
> Si el cliente no tiene ninguna factura pagada, el campo retorna `NULL` (mostrado como `0.00` en la UI).

---

## `wizard/sng_customer_ar_report_wizard.py` — `CustomerArReportWizard`

**Modelo:** `customer.ar.report.wizard` (TransientModel)  
**Descripción:** Formulario de parámetros para filtrar el reporte antes de abrirlo.

### Campos

| Campo | Tipo | Descripción | Default |
|---|---|---|---|
| `date_from` | `Date` | Límite inferior del rango de fechas de factura. | — |
| `date_to` | `Date` | Límite superior del rango de fechas de factura. | — |
| `company_id` | `Many2one(res.company)` | Filtra por compañía. | `env.company` |
| `partner_id` | `Many2one(res.partner)` | Filtra por un cliente específico. | — |
| `only_with_balance` | `Boolean` | Si `True`, incluye solo clientes con saldo pendiente (`amount_due > 0`). | `False` |

### Métodos

#### `action_view_report()`
- **Ámbito:** instancia única (`ensure_one`).
- Construye dinámicamente un dominio de búsqueda a partir de los campos del wizard:

  | Campo wizard | Condición de dominio añadida |
  |---|---|
  | `date_from` | `('invoice_date_max', '>=', date_from)` |
  | `date_to` | `('invoice_date_min', '<=', date_to)` |
  | `company_id` | `('company_id', '=', company_id.id)` |
  | `partner_id` | `('partner_id', '=', partner_id.id)` |
  | `only_with_balance = True` | `('amount_due', '>', 0)` |

  > **Nota de diseño:** El filtro de fechas usa `invoice_date_max` y `invoice_date_min` (y no `invoice_date` directamente), ya que la vista SQL agrupa por cliente y no expone una fecha de factura individual en el GROUP BY.

- Retorna una acción `ir.actions.act_window` que abre el modelo `customer.ar.report` con el dominio calculado en modo `list,pivot`.

---

## Vistas

### `views/sng_customer_ar_report_views.xml`

#### Vista Lista (`view_customer_ar_report_tree`)
- Modelo: `customer.ar.report`
- Atributos: `create="false" edit="false" delete="false"` — Solo lectura.
- Columnas visibles por defecto: `partner_code`, `partner_id`, `amount_invoiced`, `amount_due`, `avg_days_to_pay`.
- Columnas opcionales (`optional="show"`): `payment_term_id`, `company_id` *(multi-company)*, `invoice_count`, `paid_invoice_count`.
- Columnas ocultas por defecto (`optional="hide"`): `invoice_date_min`, `invoice_date_max`.
- `amount_invoiced` y `amount_due` muestran subtotales de columna (`sum`).

#### Vista Pivot (`view_customer_ar_report_pivot`)
- Dimensión de filas: `partner_id`.
- Medidas: `amount_invoiced`, `amount_due`, `avg_days_to_pay`.

#### Vista de Búsqueda (`view_customer_ar_report_search`)
- Campos de búsqueda: `partner_code`, `partner_id`, `company_id` *(multi-company)*.
- **Filtros rápidos de fecha:**

  | Filtro | Domain |
  |---|---|
  | Este Mes | `invoice_date_max >= primer día del mes` AND `invoice_date_min <= hoy` |
  | Mes Pasado | `invoice_date_max >= primer día del mes anterior` AND `invoice_date_min <= último día del mes anterior` |
  | Este Año | `invoice_date_max >= 1 enero del año actual` AND `invoice_date_min <= hoy` |

- **Filtro de saldo:** `amount_due > 0`.
- **Agrupaciones:** por `partner_id` y por `company_id` *(solo multi-company)*.

#### Acción (`action_customer_ar_report`)
- Modelo: `customer.ar.report`
- Modos: `list,pivot`
- Usa `view_customer_ar_report_search` como vista de búsqueda.
- El filtro "Solo con Saldo" **no** está activo por defecto (`search_default_filter_only_with_balance: 0`).

#### Menú
- Ubicación: `Contabilidad → Informes → CxC por Cliente` (sequence 100)

---

### `views/sng_customer_ar_report_wizard_views.xml`

#### Vista Formulario del Wizard (`view_customer_ar_report_wizard_form`)
- Dos grupos en el formulario:
  - **Rango de Fechas:** `date_from`, `date_to`
  - **Filtros:** `company_id` *(solo multi-company)*, `partner_id`, `only_with_balance`
- Botones: **"Ver Reporte"** (llama `action_view_report`) y **"Cancelar"**.

#### Acción del Wizard (`action_customer_ar_report_wizard`)
- Abre el wizard en una ventana modal (`target: new`).

#### Menú
- Ubicación: `Contabilidad → Informes → CxC por Cliente (Filtro)` (sequence 101)

---

## Seguridad

| Regla | Modelo | Grupo | R | W | C | D |
|---|---|---|---|---|---|---|
| `customer.ar.report.invoice` | `customer.ar.report` | `account.group_account_invoice` | ✓ | ✗ | ✗ | ✗ |
| `customer.ar.report.user` | `customer.ar.report` | `account.group_account_user` | ✓ | ✗ | ✗ | ✗ |
| `customer.ar.report.wizard.invoice` | `customer.ar.report.wizard` | `account.group_account_invoice` | ✓ | ✓ | ✓ | ✓ |
| `customer.ar.report.wizard.user` | `customer.ar.report.wizard` | `account.group_account_user` | ✓ | ✓ | ✓ | ✓ |

---

## Flujo de Uso

```
Usuario abre menú
  │
  ├─ "CxC por Cliente"          ── abre reporte directamente sin filtros previos
  │
  └─ "CxC por Cliente (Filtro)" ── abre el Wizard primero
          │
          ▼
    CustomerArReportWizard (formulario modal)
    [date_from, date_to, company_id, partner_id, only_with_balance]
          │
          ▼ action_view_report()
    Construye domain dinámico
          │
          ▼
    CustomerArReport (SQL VIEW)
    ┌──────────────────────────────────────────────┐
    │  account_move (out_invoice, posted)          │
    │  + LATERAL subconsulta para fecha de pago   │
    │  GROUP BY (partner_id, company_id)           │
    └──────────────────────────────────────────────┘
          │
          ▼
    Vista Lista / Pivot con filtros aplicados
    (Exportable a Excel con botón estándar de Odoo)
```

---

## Diagrama de Tablas SQL Involucradas

```
account_move (am)
    ├── JOIN res_company (rc)        → currency_id
    ├── JOIN res_partner (rp)        → unique_id, name
    └── LEFT JOIN LATERAL (
            account_partial_reconcile (apr)
                └── JOIN account_move_line (aml_inv)
                        └── JOIN account_account (aa)
                            WHERE account_type = 'asset_receivable'
        ) pay_dates
```
