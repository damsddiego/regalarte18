# -*- coding: utf-8 -*-
# Ejecutar en Odoo Shell:  odoo-bin shell -d <tu_db>

import os
import re

import xlrd  # <-- usamos xlrd para leer .xls

PARTNER = env['res.partner']

# ===== Config =====
NOMBRE_HOJA = 'Clientes'  # Cambia si tu hoja se llama distinto
COMMIT_INTERVAL = 50  # commit cada N filas
DEFAULT_XLS = 'clientes.xls'  # tu archivo .xls


# ===== Utils =====
def _normalize_header(s):
    return re.sub(r'\s+', ' ', str(s or '').strip().lower())


def _resolve_path(filename):
    """Devuelve ruta existente. Prioriza carpeta del script (__file__), luego CWD, luego carpeta padre."""
    if os.path.isabs(filename):
        if not os.path.exists(filename):
            raise FileNotFoundError(f"No se encontró el archivo absoluto: {filename}")
        return filename
    tried = []
    base_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    p1 = os.path.join(base_dir, filename);
    tried.append(p1)
    p2 = os.path.join(os.getcwd(), filename);
    tried.append(p2)
    p3 = os.path.join(os.path.dirname(base_dir), filename);
    tried.append(p3)
    for p in tried:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("No se encontró el archivo '{0}'. Probé:\n- {1}".format(filename, "\n- ".join(tried)))


def _find_field(model, candidates):
    fields = env[model]._fields
    for c in candidates:
        if c in fields:
            return c
    return None


# ===== Opcional: tipos de identificación CR (si el módulo existe) =====
def _safe_ref(xmlid):
    try:
        return env.ref(xmlid)
    except ValueError:
        return False


id_type_map = {
    '01': _safe_ref("cr_electronic_invoice.Identificationtype_01"),  # FÍSICA
    '02': _safe_ref("cr_electronic_invoice.Identificationtype_02"),  # JURÍDICA
    '03': _safe_ref("cr_electronic_invoice.Identificationtype_03"),  # DIMEX
    '04': _safe_ref("cr_electronic_invoice.Identificationtype_04"),  # NITE
    '10': _safe_ref("cr_electronic_invoice.Identificationtype_06"),  # NO CONTRIBUYENTE (si existe)
}
id_type_field = _find_field('res.partner', ['identification_id',
                                            'l10n_latam_identification_type_id'])

country_cr = _safe_ref("base.cr")  # Costa Rica

# ===== Input archivo =====
ARCHIVO_IN = input(f"📄 Nombre del XLS (enter = {DEFAULT_XLS}): ").strip() or DEFAULT_XLS
ARCHIVO = _resolve_path(ARCHIVO_IN)
print(f"📂 Usando archivo: {ARCHIVO}")

# ¿Importar como cliente, proveedor o ambos?
tipo_entidad = input("👤 ¿Deseas importar como 1=Cliente, 2=Proveedor, 3=Ambos? (enter=1): ").strip() or '1'
if tipo_entidad not in {'1', '2', '3'}:
    raise ValueError("Solo puedes ingresar 1 (cliente), 2 (proveedor) o 3 (ambos).")

es_cliente = tipo_entidad in {'1', '3'}
es_proveedor = tipo_entidad in {'2', '3'}

# ===== Cargar libro / hoja .XLS con xlrd =====
book = xlrd.open_workbook(ARCHIVO)
sheet = None
for sh in book.sheets():
    if sh.name == NOMBRE_HOJA:
        sheet = sh
        break
if sheet is None:
    raise ValueError(f"La hoja '{NOMBRE_HOJA}' no existe. Hojas: {[sh.name for sh in book.sheets()]}")

# Leer encabezados
headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
norm_headers = [_normalize_header(h) for h in headers]

# Mapeo de columnas: COD_CLIE, NOMBRE, CEDULA, TIPO_CEDULA, PAIS
header_map = {
    'cod_clie': 'client_code',
    'nombre': 'name',
    'cedula': 'vat',
    'tipo_cedula': 'id_type',
    'pais': 'country_code',
    'nombre_facturar_edi': '',
    'cod_clase': '',
    'plazo': '',
    'nivel_precio': '',
    'cod_ruta': '',
    'cod_vend': '',
    'bodega_consignacion': '',
    'telefono': '',
    'telefono_2': '',
    'cod_prov': '',
    'cod_cant': '',
    'cod_dist': '',
    'direccion': '',
    'excento': '',
    'desc_fijo': '',
    'porc_exento': '',
    'limite_credito': '',
    'saldo': '',
    'fecha_ult_comp': '',
    'fecha_ultima_fact': '',
    'e_mail': 'email',
    'e_mail_cortesia': '',
    'correo2': 'email',
    'correo3': 'email',
    'notas1': 'comment',
    'notas2': 'comment',
    'notas3': 'comment',
    'notas5': 'comment',
}

idx = {}
for i, h in enumerate(norm_headers):
    if h in header_map:
        idx[header_map[h]] = i


def _getv(row_index, key):
    col = idx.get(key, None)
    if col is None:
        return None
    try:
        return sheet.cell_value(row_index, col)
    except IndexError:
        return None


# ===== Procesamiento =====
errores = []
logs = []
procesados = 0
created_total = 0
updated_total = 0
skipped_no_keys = 0
skipped_multi = 0
commit_counter = 0

for r in range(1, sheet.nrows):  # desde fila 2 (índice 1)
    procesados += 1
    try:
        client_code = _getv(r, 'client_code')
        client_code = str(client_code).strip() if client_code is not None else ''
        name = _getv(r, 'name')
        name = str(name).strip() if name is not None else ''
        vat = _getv(r, 'vat')
        vat = str(vat).strip() if vat is not None else ''
        id_type_code = str(_getv(r, 'id_type') or '').strip()

        if not client_code and not name and not vat:
            skipped_no_keys += 1
            logs.append(f"[{r + 1}] sin COD_CLIE, NOMBRE ni CEDULA -> saltado")
            continue

        # Buscar partner existente por client_code
        partner = False
        if client_code:
            found = PARTNER.search([('client_code', '=', client_code)])
            if len(found) == 1:
                partner = found[0]
            elif len(found) > 1:
                skipped_multi += 1
                logs.append(f"[{r + 1}] client_code={client_code} múltiples partners {found.ids} -> saltado")
                continue

        vals = {}

        if name:
            vals['name'] = name
        if client_code:
            vals['client_code'] = client_code
        if vat:
            vals['vat'] = vat

        # Cliente / proveedor
        current_customer_rank = partner.customer_rank if partner else 0
        current_supplier_rank = partner.supplier_rank if partner else 0
        if es_cliente:
            vals['customer_rank'] = max(1, current_customer_rank or 0)
        if es_proveedor:
            vals['supplier_rank'] = max(1, current_supplier_rank or 0)

        # Tipo de persona y tipo de identificación (unificado)
        if id_type_code in id_type_map and id_type_map[id_type_code]:
            if id_type_field:
                vals[id_type_field] = id_type_map[id_type_code].id

            # Persona física
            if id_type_code in ('01', '1'):
                vals['company_type'] = 'person'
                vals['is_company'] = False
            else:
                vals['company_type'] = 'company'
                vals['is_company'] = True

        # País: fija CR (puedes ajustar si necesitas leer la columna)
        if country_cr:
            vals['country_id'] = country_cr.id

        # Crear / actualizar
        if partner:
            partner.with_context(tracking_disable=True).write(vals)
            updated_total += 1
            print(f"[{r + 1}] ✅ ACTUALIZADO client_code={client_code or '-'} name='{name}' -> {vals}")
        else:
            if 'company_type' not in vals:
                vals.setdefault('company_type', 'company')
                vals.setdefault('is_company', True)
            partner = PARTNER.create(vals)
            created_total += 1
            print(f"[{r + 1}] 🆕 CREADO client_code={client_code or '-'} name='{name}' -> {vals}")

    except Exception as e:
        errores.append(f"[{r + 1}] ❌ Error client_code={client_code or '-'} name='{name}' -> {e}")
        print(errores[-1])

    # Commits por lotes
    commit_counter += 1
    if commit_counter >= COMMIT_INTERVAL:
        env.cr.commit()
        commit_counter = 0

# Commit final
if commit_counter > 0:
    env.cr.commit()

# ===== Logs / Errores =====
base_dir = os.getcwd()
ruta_errores = os.path.join(base_dir, 'errores_importacion_clientes.txt')
ruta_log = os.path.join(base_dir, 'import_clientes_log.txt')

if errores:
    with open(ruta_errores, 'w', encoding='utf-8') as f:
        f.write('\n'.join(errores))
    print(f"⚠️ {len(errores)} errores guardados en: {ruta_errores}")

with open(ruta_log, 'w', encoding='utf-8') as f:
    f.write('\n'.join(logs))
print(f"📝 Log de proceso en: {ruta_log}")

# ===== Resumen =====
print("=== RESUMEN CLIENTES ===")
print(f"Procesados: {procesados}")
print(f"Creados: {created_total}")
print(f"Actualizados: {updated_total}")
print(f"Saltados sin claves (COD_CLIE/NOMBRE/CEDULA): {skipped_no_keys}")
print(f"Saltados por múltiples coincidencias: {skipped_multi}")
print(f"Errores: {len(errores)}")
