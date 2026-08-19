# Notificación de Falta de Stock en Entregas

**Versión:** 18.0.1.0.0  
**Autor:** SNG  
**Licencia:** LGPL-3  
**Categoría:** Inventario / Stock

---

## Descripción

Este módulo notifica automáticamente a usuarios configurados cuando una entrega (`stock.picking`) no puede validarse por falta de stock en la ubicación origen.

La notificación se envía simultáneamente por:

- **Chat de Odoo (Discuss):** mensaje en el chatter del picking mencionando a los usuarios.
- **Correo electrónico:** email detallado con los productos faltantes.
- **Actividad:** tarea en la bandeja de actividades de cada usuario configurado.

---

## Dependencias

- `stock`
- `mail`

---

## Instalación

1. Verifica que la ruta `regalarte/` esté incluida en el `addons_path` de tu archivo de configuración de Odoo (`odoo.conf`).
2. Instala el módulo desde la lista de aplicaciones o mediante línea de comandos:

```bash
python odoo18/odoo-bin -c odoo.conf -i sng_stock_picking_notification -d NOMBRE_BD --stop-after-init
```

3. Reinicia el servidor Odoo si es necesario.

---

## Configuración

1. Ve a **Ajustes > Inventario**.
2. Busca el bloque **Notificaciones de Stock**.
3. En el campo **Usuarios a notificar por falta de stock**, selecciona los usuarios que recibirán las alertas.

> **Nota:** La configuración es por compañía. Si tienes un entorno multi-compañía, define los usuarios en cada compañía según corresponda.

---

## Funcionamiento

### Verificación preventiva

Cada vez que se presiona el botón **Validar** en una entrega, el módulo verifica **antes** de procesarla si existe stock suficiente en la ubicación origen para cada producto almacenable.

Solo aplica a entregas cuya ubicación origen sea de tipo **Interna** o **Tránsito**, evitando notificaciones innecesarias en recepciones de proveedor.

### Criterio de falta de stock

Para cada línea de movimiento (`stock.move`) que no esté en estado `done` o `cancel`:

- Se compara la cantidad a mover (`quantity` o `product_uom_qty` si no se ha registrado cantidad hecha) contra la cantidad disponible en la ubicación origen.
- Si la cantidad disponible es menor a la requerida, se considera stock insuficiente.

### Envío de notificaciones

Si se detecta al menos un producto con stock insuficiente, se envían las siguientes notificaciones **antes** de que Odoo procese la validación:

| Canal | Descripción |
|-------|-------------|
| **Chatter / Discuss** | Mensaje publicado en el picking mencionando a los partners de los usuarios configurados. |
| **Correo** | Email con asunto *"Alerta: Falta de stock en entrega [Nombre]"* y detalle de productos faltantes. |
| **Actividades** | Tipo *"Por hacer"* asignada a cada usuario configurado, vinculada al picking. |

---

## Estructura técnica

```
sng_stock_picking_notification/
├── __init__.py
├── __manifest__.py
├── README.md
├── data/
│   └── mail_template_data.xml          # Plantilla de correo electrónico
├── models/
│   ├── __init__.py
│   ├── res_company.py                  # Campo Many2many de usuarios en compañía
│   ├── res_config_settings.py          # Expone el campo en Ajustes
│   └── stock_picking.py                # Hereda button_validate y lógica de notificación
└── views/
    └── res_config_settings_views.xml   # Vista heredada de Ajustes
```

### Modelos

#### `res.company`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `stock_notification_user_ids` | `Many2many` → `res.users` | Usuarios que recibirán notificaciones por falta de stock. |

#### `res.config.settings`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `stock_notification_user_ids` | `Many2many` (related) | Expone el campo de la compañía en la interfaz de ajustes. |

#### `stock.picking`

| Método | Descripción |
|--------|-------------|
| `button_validate()` | Heredado. Verifica stock y envía notificaciones antes de llamar al método original. |
| `_sng_check_stock_availability()` | Retorna lista de movimientos con stock insuficiente. |
| `_sng_send_stock_notification()` | Envía chatter, correo y actividades a los usuarios configurados. |

---

## Consideraciones

- El picking continúa su flujo normal después de la notificación. Si Odoo permite crear un backorder parcial, lo hará, pero los usuarios ya habrán sido alertados.
- Si un usuario intenta validar repetidamente una entrega con falta de stock, se generará una notificación en cada intento.
- La plantilla de correo se crea con `noupdate="1"` para permitir personalizaciones sin que se sobrescriban al actualizar el módulo.

---

## Changelog

### 18.0.1.0.0
- Creación inicial del módulo.
- Soporte para notificaciones por chatter, correo y actividades.
- Configuración de usuarios notificados por compañía.
