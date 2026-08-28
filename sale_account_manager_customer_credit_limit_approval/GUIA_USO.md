# 📘 Guía de Uso: Aprobación de Límite de Crédito

## Módulo: `sale_account_manager_customer_credit_limit_approval`

---

## 📋 Resumen Ejecutivo

Este módulo implementa un **sistema de gestión de límites de crédito** con flujo de aprobación multinivel para órdenes de venta en Odoo 18. Permite controlar el riesgo financiero al establecer límites configurables por cliente y requerir aprobaciones cuando se exceden dichos límites.

| Atributo | Valor |
|----------|-------|
| **Versión** | 18.0.0.0 |
| **Autor** | TechUltra Solutions Private Limited |
| **Licencia** | OPL-1 (Odoo Proprietary License) |
| **Dependencias** | `sale_management` |

### ✨ Características Principales

- 🔒 **Doble umbral**: Límite de advertencia y límite de bloqueo por cliente
- 🔄 **Flujo de aprobación de 2 niveles**: Gerente de Ventas → Equipo Financiero
- 📧 **Notificaciones automáticas** por email en cada etapa
- ⚠️ **Detección de facturas vencidas** con alertas visuales
- 🧮 **Cálculo dinámico** de saldo pendiente (facturas + órdenes sin facturar)

---

## 🏗️ Arquitectura del Módulo

### Modelos Extendidos

| Modelo | Descripción |
|--------|-------------|
| `res.partner` | Campos de configuración de límite de crédito |
| `sale.order` | Estados de aprobación y lógica de validación |
| `res.company` | Email del contador para notificaciones |

### Nuevos Modelos

| Modelo | Tipo | Descripción |
|--------|------|-------------|
| `warning.wizard` | Transitorio | Wizard de advertencia para bloqueos suaves |

### Flujo de Dependencias

```
base
  └── sale
       └── sale_management
                └── sale_account_manager_customer_credit_limit_approval
```

---

## ⚙️ Configuración del Módulo

### 1️⃣ Configuración del Cliente

Navegue a **Contactos → Seleccione un cliente → pestaña Ventas y Compras** (o área de Contabilidad):

| Campo | Tipo | Descripción |
|-------|------|-------------|
| **Active Credit** (`credit_check`) | Booleano | Activa la funcionalidad de límite de crédito |
| **Warning Amount** (`credit_warning`) | Monetario | Umbral de advertencia (no bloquea) |
| **Blocking Amount** (`credit_blocking`) | Monetario | Umbral de bloqueo (requiere aprobación) |

#### Reglas de Validación

```python
# El sistema valida automáticamente:
- Warning Amount ≤ Blocking Amount
- Ambos montos deben ser ≥ 0
```

#### Cálculo del Saldo Pendiente (`amount_due`)

El sistema calcula el saldo pendiente del cliente sumando:

1. **Facturas publicadas** (`posted`) de tipo `out_invoice` y `out_refund`
2. **Órdenes de venta confirmadas** que aún no tienen facturas
3. **Facturas en borrador** asociadas a órdenes de venta

> **Nota**: Excluye facturas con estado tributario `rechazado` o `firma_invalida`

### 2️⃣ Configuración de la Compañía

Navegue a **Ajustes → Usuarios y Compañías → Compañías → Seleccione su compañía**:

| Campo | Descripción |
|-------|-------------|
| **Accountant Email** | Email del equipo financiero para recibir notificaciones de aprobación |

---

## 🔄 Flujo de Trabajo de Aprobación

### Diagrama de Estados

```
┌─────────┐    ┌─────────┐    ┌──────────────────┐
│  draft  │───▶│  sent   │───▶│ sales_approval   │
│(Cotiz.) │    │(Enviada)│    │(Espera Ventas)   │
└─────────┘    └─────────┘    └────────┬─────────┘
                                       │
                      ┌────────────────┴────────────────┐
                      │                                 │
                      ▼                                 ▼
            ┌──────────────────┐             ┌──────────────────┐
            │      reject      │             │finance_approval  │
            │    (Rechazado)   │             │(Espera Finanzas) │
            └──────────────────┘             └────────┬─────────┘
                                                      │
                                   ┌──────────────────┴──────────────────┐
                                   │                                     │
                                   ▼                                     ▼
                         ┌──────────────────┐                 ┌──────────────────┐
                         │      reject      │                 │     approved     │
                         │    (Rechazado)   │                 │  (Aprobado Fin.) │
                         └──────────────────┘                 └────────┬─────────┘
                                                                      │
                                                                      ▼
                                                               ┌─────────────┐
                                                               │    sale     │
                                                               │  (Pedido)   │
                                                               └─────────────┘
```

### Roles en el Flujo

| Rol | Grupo de Odoo | Función |
|-----|---------------|---------|
| **Vendedor/ERP Manager** | `base.group_erp_manager` | Inicia el flujo de aprobación |
| **Gerente de Ventas** | `sales_team.group_sale_manager` | Primer nivel de aprobación/rechazo |
| **Equipo Financiero** | `account.group_account_invoice` | Aprobación final/rechazo |

### Proceso Paso a Paso

#### Paso 1: Detección de Exceso de Crédito

Cuando un vendedor intenta confirmar una orden que excede el límite de bloqueo:

```
┌─────────────────────────────────────────────┐
│  ❌ Error: "Can not confirm the respective  │
│     S.O as Customer has crossed their       │
│     Approved credit limit by $X.XX          │
│     Please seek for approval to proceed"    │
└─────────────────────────────────────────────┘
```

#### Paso 2: Iniciar Aprobación

El botón **"Credit Limit Approval"** aparece para usuarios con rol ERP Manager:

- Estado cambia a: `sales_approval`
- Se envía email al Gerente de Ventas asignado al cliente
- Se registra mensaje en el chatter

#### Paso 3: Aprobación de Ventas

El Gerente de Ventas ve el botón **"Approve"**:

- Estado cambia a: `finance_approval`
- Se envía email al equipo financiero (usando `accountant_email`)
- Se registra mensaje en el chatter

#### Paso 4: Aprobación Final

El equipo financiero ve el botón **"Approve"**:

- Estado cambia a: `approved`
- Campo `is_credit_limit_final_approved` = `True`
- El vendedor ahora puede confirmar la orden

#### Paso 5: Confirmación

El vendedor puede confirmar la orden normalmente (estado `sale`).

### Flujo de Rechazo

En cualquier etapa de aprobación, los aprobadores pueden **"Reject"**:

- Estado cambia a: `reject`
- Se envía email de notificación al vendedor
- Se registra mensaje en el chatter indicando quién rechazó

---

## 🎛️ Sistema de Control de Crédito (3 Escenarios)

### Escenario 1: Procesamiento Normal ✅

**Condiciones:**
- `(saldo_pendiente + total_orden) ≤ límite_bloqueo`
- Cliente NO tiene facturas vencidas

**Acción:**
- Confirmación normal sin intervención
- Aprobaciones requeridas: **0**

---

### Escenario 2: Advertencia (Bloqueo Suave) ⚠️

**Condiciones (cualquiera de estas):**

| Caso | Condición |
|------|-----------|
| **A** | `límite_advertencia ≤ saldo_pendiente < límite_bloqueo` |
| **B** | Cliente tiene facturas vencidas (incluso si no excede límites) |
| **C** | Cliente tiene facturas vencidas Y excede advertencia |

**Acción:**
- Aparece **Wizard de Advertencia** con mensaje contextual:

| Situación | Mensaje |
|-----------|---------|
| Solo facturas vencidas | "Customer has overdue invoices, Do You want to continue?" |
| Facturas vencidas + advertencia | "Customer has overdue invoices and warning limit exceeded, Do You want to continue?" |
| Solo advertencia | "Customer warning limit exceeded, Do You want to continue?" |

**Botones:**
- **Yes**: Continúa con la confirmación
- **No**: Cancela la acción

**Aprobaciones requeridas:** **0** (solo confirmación del usuario)

---

### Escenario 3: Bloqueo Duro 🚫

**Condiciones:**
- `(saldo_pendiente + total_orden) > límite_bloqueo`
- Ó `límite_bloqueo ≤ saldo_pendiente` sin facturas previas

**Acción:**
- Se previene la confirmación
- Se muestra error con monto excedido
- Se requiere flujo de aprobación de 2 niveles

**Aprobaciones requeridas:** **2** (Gerente de Ventas + Equipo Financiero)

---

## 📊 Detección de Facturas Vencidas

### Lógica de Detección

El sistema busca facturas con estos criterios:

```python
self.env['account.move'].search([
    ('partner_id', '=', cliente_id),
    ('state', '=', 'posted'),                    # Factura confirmada
    ('payment_state', 'in', ['not_paid', 'partial']),  # No pagada/Parcial
    ('move_type', 'in', ['out_invoice', 'out_refund']), # Cliente
    ('invoice_date_due', '<', hoy),              # Fecha vencida pasada
])
```

### Campos Computados

| Campo | Modelo | Descripción |
|-------|--------|-------------|
| `has_overdue_invoices` | `res.partner` / `sale.order` | Booleano: ¿Tiene facturas vencidas? |
| `overdue_amount` | `res.partner` / `sale.order` | Monto total de facturas vencidas |

### Alertas Visuales

#### Banner Rojo (Facturas Vencidas)

```
┌─────────────────────────────────────────────────┐
│  ⚠️ Warning: This customer has overdue invoices!│
└─────────────────────────────────────────────────┘
```

- Color: Rojo (`alert-danger`)
- Visible en estados: `draft`, `sent`
- Icono: FontAwesome exclamation-triangle

#### Banner Amarillo (Límite Excedido)

```
┌─────────────────────────────────────────────────┐
│  Customer Blocking Limit: $15,000.00            │
│  Customer Due Amount: $14,000.00                │
└─────────────────────────────────────────────────┘
```

- Color: Amarillo (`alert-warning`)
- Visible cuando `is_credit_limit_approval == True`

---

## 🔐 Permisología y Seguridad

### Permisos de Modelo (`ir.model.access.csv`)

| Modelo | Grupo | Lectura | Escritura | Creación | Eliminación |
|--------|-------|---------|-----------|----------|-------------|
| `warning.wizard` | `base.group_user` | ✅ | ✅ | ✅ | ✅ |

> El wizard de advertencia es transitorio y accesible para todos los usuarios internos.

### Permisos por Botón (Vistas XML)

| Botón | Grupo Requerido | Estado Visible | Acción |
|-------|-----------------|----------------|--------|
| **Credit Limit Approval** | `base.group_erp_manager` | `draft`, `sent` | Inicia flujo |
| **Approve** (Sales) | `sales_team.group_sale_manager` | `sales_approval` | Aprueba nivel 1 |
| **Approve** (Finance) | `account.group_account_invoice` | `finance_approval` | Aprueba nivel 2 |
| **Reject** (Sales) | `sales_team.group_sale_manager` | `sales_approval` | Rechaza |
| **Reject** (Finance) | `account.group_account_invoice` | `finance_approval` | Rechaza |

### Consideraciones de Seguridad

> ⚠️ **Nota**: Los campos de configuración de límite de crédito (`credit_check`, `credit_warning`, `credit_blocking`) **no tienen restricción de grupo** en la vista actual. Cualquier usuario que pueda editar contactos puede modificarlos.

---

## 📧 Sistema de Notificaciones

### Plantillas de Email

| ID Técnico | Destinatario | Momento de Envío |
|------------|--------------|------------------|
| `sale_order_credit_limit_approval_sales_manager` | Vendedor asignado al cliente | Al iniciar aprobación |
| `sale_order_credit_limit_approval_account_manager` | `accountant_email` de la compañía | Al aprobar ventas |
| `sale_order_credit_limit_approved` | Vendedor de la orden | (Definida pero no usada en el flujo actual) |

### Contenido de Notificaciones

#### Email al Gerente de Ventas

```
Asunto: Sales manager approval for Customer credit limit
Para: [email del vendedor asignado al cliente]

[Cliente] has used all their credit limit, please approve the 
request to override the blocking of order.

[Link a la orden de venta]
```

#### Email al Equipo Financiero

```
Asunto: Finance manager approval for Customer credit limit
Para: [accountant_email de la compañía]

Please overwrite the Credit limit for [Cliente], it has already 
been approved by [Gerente de Ventas].

[Link a la orden de venta]
```

#### Email de Rechazo

```
Asunto: Customer credit limit rejected
Para: [email del vendedor de la orden]

This email is to notify that Quotation number [N°] which belongs 
to [Cliente] has been rejected by [Nombre del Rechazador], 
please reach him for further clarifications.
```

---

## 🖥️ Interfaz de Usuario

### Panel de Información de Crédito

Ubicado en el formulario de orden de venta, debajo de los detalles del pedido:

```
┌─────────────────────────────────────────────────┐
│  Customer Credit Information                     │
├─────────────────────────────────────────────────┤
│  Customer Warning Limit:    $10,000.00          │
│  Credit Limit:              $15,000.00          │
│  Amount Due:                $8,500.00           │
│  Overdue Amount:            $2,500.00  [ROJO]   │
│  Customer Payment Term:     30 Net Days         │
└─────────────────────────────────────────────────┘
```

**Características:**
- Solo visible cuando `partner_id.credit_check == True`
- Todos los campos son de solo lectura
- El monto vencido aparece en rojo si es > 0

### Estados Adicionales en Órdenes de Venta

| Estado | Color | Descripción |
|--------|-------|-------------|
| `sales_approval` | Azul | Esperando aprobación del Gerente de Ventas |
| `finance_approval` | Azul | Esperando aprobación del Equipo Financiero |
| `approved` | Verde | Aprobado, listo para confirmar |
| `reject` | Rojo | Rechazado por aprobador |

### Estados de Confirmación Modificados

Los botones de confirmación se modifican para respetar el flujo:

- **Confirmar** (enviar por email): Visible en `draft` solo si `is_credit_limit_approval == False`
- **Confirmar**: Visible en `sent`, `approved`

---

## 📝 Ejemplos de Casos de Uso

### Caso 1: Cliente con Facturas Vencidas

**Datos del Cliente:**
- Límite Advertencia: $10,000
- Límite Bloqueo: $15,000
- Saldo Actual: $5,000
- **Factura vencida: $2,000**

**Nueva Orden:** $3,000

**Flujo:**
1. Aparece banner rojo: "Warning: This customer has overdue invoices!"
2. Vendedor hace clic en "Confirmar"
3. Wizard: "Customer has overdue invoices, Do You want to continue?"
4. Vendedor hace clic en "Yes"
5. Orden se confirma normalmente

**Resultado:** Saldo final = $8,000 (todavía bajo el límite de advertencia)

---

### Caso 2: Advertencia Excedida + Facturas Vencidas

**Datos del Cliente:**
- Límite Advertencia: $10,000
- Límite Bloqueo: $15,000
- Saldo Actual: $9,000
- **Factura vencida: $3,000**

**Nueva Orden:** $2,000

**Flujo:**
1. Aparece banner rojo de facturas vencidas
2. Vendedor hace clic en "Confirmar"
3. Wizard: "Customer has overdue invoices and warning limit exceeded, Do You want to continue?"
4. Vendedor hace clic en "Yes"
5. Orden se confirma

**Resultado:** Saldo final = $11,000 (excede advertencia pero no bloqueo)

---

### Caso 3: Bloqueo Duro con Flujo Completo

**Datos del Cliente:**
- Límite Bloqueo: $15,000
- Saldo Actual: $14,000
- Sin facturas vencidas

**Nueva Orden:** $3,000

**Flujo:**
1. Vendedor hace clic en "Confirmar"
2. **Error**: "Can not confirm... exceeds customer's credit limit by $2,000"
3. Botón "Credit Limit Approval" aparece (ERP Manager)
4. ERP Manager hace clic → Estado: `sales_approval`
5. Email enviado al Gerente de Ventas
6. Gerente de Ventas hace clic en "Approve" → Estado: `finance_approval`
7. Email enviado al equipo financiero
8. Equipo financiero hace clic en "Approve" → Estado: `approved`
9. Vendedor hace clic en "Confirmar" → Estado: `sale`

**Resultado:** Orden confirmada con aprobación de 2 niveles

---

## 🔧 Notas Técnicas

### Campos Extendidos

#### `res.partner`

```python
credit_check          = fields.Boolean('Active Credit')
credit_warning        = fields.Monetary('Warning Amount')
credit_blocking       = fields.Monetary('Blocking Amount')
amount_due            = fields.Monetary('Due Amount', compute='_compute_amount_due')
has_overdue_invoices  = fields.Boolean(compute='_compute_has_overdue_invoices')
overdue_amount        = fields.Monetary(compute='_compute_overdue_amount')
```

#### `sale.order`

```python
state                    = fields.Selection([...])  # Estados adicionales
amount_due               = fields.Monetary(related='partner_id.amount_due')
customer_blocking_limit  = fields.Monetary(related='partner_id.credit_blocking')
has_overdue_invoices     = fields.Boolean(related='partner_id.has_overdue_invoices')
overdue_amount           = fields.Monetary(related='partner_id.overdue_amount')
is_credit_limit_approval = fields.Boolean(compute='_compute_customer_credit_limit')
is_credit_limit_final_approved = fields.Boolean()
available_credit         = fields.Monetary(compute='_compute_available_credit')
```

#### `res.company`

```python
accountant_email = fields.Char(string='Accountant email')
```

### Métodos Clave

| Método | Modelo | Descripción |
|--------|--------|-------------|
| `action_confirm()` | `sale.order` | Sobrescrito para validar límites antes de confirmar |
| `send_credit_limit_approval()` | `sale.order` | Inicia flujo de aprobación |
| `approved_credit_limit_from_sales_manager()` | `sale.order` | Aprueba nivel 1 |
| `approved_credit_limit_from_account_manager()` | `sale.order` | Aprueba nivel 2 |
| `reject_sale_order()` | `sale.order` | Rechaza orden |
| `get_so_for_approval()` | `sale.order` | Genera URL para emails |
| `_compute_amount_due()` | `res.partner` | Calcula saldo pendiente |
| `_compute_has_overdue_invoices()` | `res.partner` | Detecta facturas vencidas |
| `_compute_overdue_amount()` | `res.partner` | Calcula monto vencido |
| `_check_credit_amount()` | `res.partner` | Valida consistencia de montos |

### Restricciones

```python
@api.constrains('credit_warning', 'credit_blocking')
def _check_credit_amount(self):
    # Valida que warning ≤ blocking
    # Valida que ambos sean ≥ 0
```

---

## 🐛 Solución de Problemas

### Problema: No aparece el botón "Credit Limit Approval"

**Causas posibles:**
1. El usuario no tiene el grupo `base.group_erp_manager`
2. La orden no está en estado `draft` o `sent`
3. El campo `is_credit_limit_approval` es `False`

**Solución:**
- Verifique que el cliente tenga `credit_check = True`
- Verifique que `(amount_due + amount_total) > customer_blocking_limit`
- Verifique los permisos del usuario

---

### Problema: No se envían los emails de aprobación

**Causas posibles:**
1. No hay email configurado en el vendedor asignado al cliente
2. No hay `accountant_email` configurado en la compañía
3. El servidor de correo no está configurado

**Solución:**
- Configure el email del vendedor en **Contactos → Vendedor → Email**
- Configure `accountant_email` en **Ajustes → Compañías**
- Verifique la configuración del servidor de correo saliente

---

### Problema: El cálculo de saldo pendiente es incorrecto

**Causas posibles:**
1. Facturas con estado tributario especial no se están filtrando correctamente
2. Órdenes de venta no facturadas no se están considerando

**Verificación:**
El sistema excluye facturas con:
- `state_tributacion` = `rechazado` o `firma_invalida`

---

### Problema: No aparece la alerta de facturas vencidas

**Causas posibles:**
1. La orden no está en estado `draft` o `sent`
2. El cliente no tiene facturas vencidas (verificar fecha de vencimiento)
3. Las facturas vencidas ya están pagadas

**Criterios de detección:**
- Factura `posted`
- `payment_state` en `not_paid` o `partial`
- `invoice_date_due < hoy`

---

### Lista de Verificación de Configuración

- [ ] Cliente tiene activado **Active Credit**
- [ ] Cliente tiene configurado **Warning Amount**
- [ ] Cliente tiene configurado **Blocking Amount** (≥ Warning)
- [ ] Compañía tiene configurado **Accountant Email**
- [ ] Vendedor asignado al cliente tiene email
- [ ] Usuarios aprobadores tienen los grupos correctos
- [ ] Servidor de correo configurado

---

## 📚 Referencias

- **Documentación Odoo**: https://www.odoo.com/documentation/18.0/
- **Módulo Original**: TechUltra Solutions Private Limited
- **Versión del Módulo**: 18.0.0.0

---

*Documento generado para el módulo `sale_account_manager_customer_credit_limit_approval`*
