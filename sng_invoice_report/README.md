# Invoice Report by Salesperson

Módulo para Odoo 18 que genera reportes de facturas agrupadas por vendedor, con soporte multicompañía, exportación a Excel/PDF y visualización en pantalla.

---

## ✨ Características

- **Filtros avanzados:** Rango de fechas, multicompañía, vendedor(es), tipo de documento, estado de pago
- **Visualización en pantalla:** Vista nativa Odoo (list, pivot, graph) con agrupación por vendedor
- **Exportación Excel:** Formato profesional con colores, subtotales y totales generales
- **Reporte PDF:** Plantilla QWeb con branding de la compañía
- **Multicompañía:** Respeta las reglas de acceso y record rules de Odoo
- **Sin `sudo()`:** Seguridad nativa, sin bypass de permisos
- **Manejo correcto de notas de crédito:** Evita doble conteo de reversiones
- **Reglas configurables de vendedor:** Reasigna el vendedor mostrado según el usuario responsable y la compañía, sin modificar las facturas

---

## 📦 Instalación

### Requisitos previos

- Odoo 18.0
- Módulos dependientes instalados:
  - `account`
  - `sales_commission_omax`
  - `sng_invoice_assigned_salesperson`
- Librería Python:
  - `xlsxwriter`

```bash
pip install xlsxwriter
```

### Instalación del módulo

1. Copia la carpeta `sng_invoice_report` a tu directorio de addons
2. Actualiza la lista de apps en Odoo
3. Busca "Invoice Report by Salesperson" e instálalo

---

## 🚀 Uso

### Acceder al reporte

1. Ve a **Invoicing > Reporting > Reporte de facturas por vendedor**
2. O usa el menú de aplicaciones y busca el reporte

### Filtros disponibles

| Filtro | Descripción |
|--------|-------------|
| **Date From / Date To** | Rango de fechas de las facturas |
| **Companies** | Selecciona una o varias compañías (limitado a tus permisos) |
| **Invoice Type** | Facturas de cliente, Notas de crédito, o Todos |
| **Payment Status** | Todos, No pagado, En pago, Pagado, Parcialmente pagado, Revertido |
| **Salespersons** | Filtra por vendedor(es) específicos. Vacío = todos |

### Acciones

- **View on Screen** — Abre la vista de facturas filtradas con agrupación por vendedor
- **Download Excel** — Descarga el reporte en formato `.xlsx`
- **Print PDF** — Genera el reporte en formato PDF

---

## 🏗️ Arquitectura

### Modelos

#### `account.move` (heredado)

Añade el campo computado `effective_salesperson_id`:

- Prioridad 1: `salesperson_id` (del módulo `sales_commission_omax`)
- Prioridad 2: `assigned_salesperson_id` (del cliente)

```python
effective_salesperson_id = fields.Many2one(
    'res.partner',
    string='Effective Salesperson',
    compute='_compute_effective_salesperson_id',
    store=True,
)
```

#### `invoice.report.wizard` (TransientModel)

Wizard principal que gestiona:

- Construcción del dominio de búsqueda (`_get_report_domain`)
- Filtrado y ordenamiento de facturas (`_filter_report_moves`, `_sort_report_moves`)
- Agrupación por vendedor con totales (`_get_report_data`)
- Generación de Excel (`action_print_excel`)
- Generación de PDF (`action_print_pdf`)
- Vista en pantalla (`action_view_on_screen`)

#### `invoice.report.salesperson.rule`

Permite configurar, por compañía, qué vendedor debe mostrar el reporte cuando
una factura tiene un usuario responsable específico. La regla solo afecta este
reporte y no modifica `salesperson_id`, facturas ni comisiones.

### Vistas

- **Wizard form** (`view_invoice_report_wizard_form`) — Interfaz de filtros y botones
- **Tree view** (`view_invoice_tree_effective_salesperson`) — Vista lista con agrupación por vendedor
- **Search view** (`view_account_invoice_filter_effective_salesperson`) — Filtros y agrupación en búsqueda

### Reportes

- **PDF** (`action_report_invoice_salesperson`) — Plantilla QWeb `report_invoice_salesperson_document`

---

## 🔒 Seguridad

### Permisos

| Grupo | Lectura | Escritura | Creación | Eliminación |
|-------|---------|-----------|----------|-------------|
| `account.group_account_invoice` | ✅ | ✅ | ✅ | ✅ |
| `account.group_account_manager` | ✅ | ✅ | ✅ | ✅ |

### Reglas

- No se utiliza `sudo()` en ninguna parte del código
- El dominio de búsqueda respeta las compañías permitidas del usuario (`env.companies`)
- Las vistas en pantalla usan el contexto nativo de Odoo con `allowed_company_ids`

---

## 🌐 Internacionalización

Idiomas soportados:

- **Español** (`es.po`)
- **Español (Costa Rica)** (`es_CR.po`)

Para recargar traducciones:

1. Modo desarrollador activado
2. **Settings > Translations > Load a Translation**
3. Selecciona el idioma y marca "Overwrite Existing Terms"

---

## 🛠️ Desarrollo

### Estructura de archivos

```
sng_invoice_report/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── account_move.py
├── wizard/
│   ├── __init__.py
│   ├── invoice_report_wizard.py
│   └── invoice_report_wizard_view.xml
├── report/
│   ├── __init__.py
│   ├── invoice_report.py
│   ├── invoice_report.xml
│   └── invoice_report_template.xml
├── views/
│   └── account_move_views.xml
├── security/
│   └── ir.model.access.csv
└── i18n/
    ├── es.po
    ├── es_CR.po
    └── sng_invoice_report.pot
```

### Convenciones de código

- Python: PEP 8, codificación UTF-8
- Nombres de clases: `PascalCase`
- Nombres de métodos/campos: `snake_case`
- XML: IDs externos en formato `nombre_modulo.id_registro`

---

## 📝 Changelog

### 18.0.2.0.0 (2026-03-09)

- Filtro multicompañía nativo
- Vista en pantalla compatible con Odoo 18 (`list` en lugar de `tree`)
- Exportación Excel y PDF adaptadas para multicompañía
- Corrección de duplicación de notas de crédito
- Campo `effective_salesperson_id` con fallback lógico
- Contexto mejorado con `allowed_company_ids`

---

## 📄 Licencia

OPL-1 (Odoo Proprietary License v1.0)

---

**Autor:** SNG Cloud  
**Sitio web:** https://www.sngcloud.com
