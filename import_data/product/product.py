# -*- coding: utf-8 -*-
# Ejecutar en Odoo Shell:  odoo-bin shell -d <tu_db>

import os
import re
import openpyxl

PRODUCT = env['product.template']
CATEGORY = env['product.category']
CABYS_PRODUCT = env['cabys.producto']  # Modelo CAByS

# ===== Config =====
NOMBRE_HOJA = 'Productos'          # cambia si tu hoja se llama distinto
COMMIT_INTERVAL = 50               # commit cada N filas
DEFAULT_XLSX = 'productos.xlsx'    # nombre por defecto

# ===== Utils =====
def _parse_number(val):
    """Convierte '1,098.41' | '1.098,41' | 1098.41 | '' -> float o None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.upper() in {'NA','N/A','NONE','NULL','-'}:
        return None
    s = s.replace(' ', '')
    if ',' in s and '.' in s:
        # 1.098,41 -> 1098.41 ; 1,098.41 -> 1098.41
        if re.search(r'^\d{1,3}(\.\d{3})+,\d{1,2}$', s):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s and '.' not in s:
        s = s.replace(',', '.') if s.count(',') == 1 else s.replace(',', '')
    try:
        return float(s)
    except Exception:
        return None

def _parse_bool(val):
    if isinstance(val, bool):
        return val
    s = str(val or '').strip().lower()
    return s in {'true','1','si','sí','yes','y','t','verdadero'}

def _normalize_header(s):
    return re.sub(r'\s+', ' ', str(s or '').strip().lower())

def _find_field(model, candidates):
    fields = env[model]._fields
    for c in candidates:
        if c in fields:
            return c
    return None

def _get_or_create_categ_by_path(path):
    """
    Crea la jerarquía si no existe. Acepta 'Padre / Hija / Nieta'.
    Devuelve record de product.category o None.
    """
    parts = [p.strip() for p in str(path or '').split('/') if str(p).strip()]
    if not parts:
        return None
    parent = None
    for name in parts:
        dom = [('name', '=', name), ('parent_id', '=', parent.id if parent else False)]
        rec = CATEGORY.search(dom, limit=1)
        if not rec:
            rec = CATEGORY.create({'name': name, 'parent_id': parent.id if parent else False})
        parent = rec
    return parent

def _resolve_path(filename):
    """Devuelve ruta existente. Prioriza carpeta del script (__file__), luego CWD, luego carpeta padre."""
    if os.path.isabs(filename):
        if not os.path.exists(filename):
            raise FileNotFoundError(f"No se encontró el archivo absoluto: {filename}")
        return filename
    tried = []
    base_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    p1 = os.path.join(base_dir, filename); tried.append(p1)
    p2 = os.path.join(os.getcwd(), filename); tried.append(p2)
    p3 = os.path.join(os.path.dirname(base_dir), filename); tried.append(p3)
    for p in tried:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("No se encontró el archivo '{0}'. Probé:\n- {1}".format(filename, "\n- ".join(tried)))

# ===== Input archivo =====
ARCHIVO_IN = input(f"📄 Nombre del XLSX (enter = {DEFAULT_XLSX}): ").strip() or DEFAULT_XLSX
ARCHIVO = _resolve_path(ARCHIVO_IN)
print(f"📂 Usando archivo: {ARCHIVO}")

# ===== Cargar libro / hoja =====
wb = openpyxl.load_workbook(ARCHIVO, data_only=True)
print(f"📑 Hojas disponibles: {wb.sheetnames}")
if NOMBRE_HOJA not in wb.sheetnames:
    raise ValueError(f"La hoja '{NOMBRE_HOJA}' no existe. Hojas: {wb.sheetnames}")
ws = wb[NOMBRE_HOJA]

# ===== Mapeo encabezados =====
header_map = {
    'costo': 'standard_price',
    'nombre': 'name',
    'precio de venta': 'list_price',
    'referencia interna': 'default_code',
    'código cabys': 'cabys_code',   # se buscará en cabys.producto.code
    'codigo cabys': 'cabys_code',
    'categoría del producto': 'categ_path',
    'categoria del producto': 'categ_path',
    'se puede comprar': 'purchase_ok',
    'se puede vender': 'sale_ok',
}
rows = list(ws.iter_rows(values_only=True))
if not rows:
    raise ValueError("La hoja está vacía.")

headers = rows[0]
norm_headers = [_normalize_header(h) for h in headers]
idx = {}
for i, h in enumerate(norm_headers):
    if h in header_map:
        idx[header_map[h]] = i

# Verifica campo Many2one en product.template
has_cabys_m2o = _find_field('product.template', ['cabys_product_id']) is not None

# ===== Procesamiento =====
errores = []
logs = []
procesados = 0
created_total = 0
updated_total = 0
skipped_no_keys = 0
skipped_multi = 0
commit_counter = 0

def _getv(row, key):
    col = idx.get(key, None)
    return row[col] if (col is not None and col < len(row)) else None

for r, row in enumerate(rows[1:], start=2):  # desde fila 2 (después de encabezados)
    procesados += 1
    try:
        ref = _getv(row, 'default_code')
        ref = str(ref).strip() if ref is not None else ''
        name = _getv(row, 'name')
        name = str(name).strip() if name is not None else ''

        if not ref and not name:
            skipped_no_keys += 1
            logs.append(f"[{r}] sin 'Referencia interna' y sin 'Nombre' -> saltado")
            continue

        # --- Buscar existente: prioridad por ref; si no, por nombre exacto ---
        prod = False
        if ref:
            found = PRODUCT.search([('default_code', '=', ref)])
            if len(found) == 1:
                prod = found[0]
            elif len(found) > 1:
                skipped_multi += 1
                logs.append(f"[{r}] REF={ref} múltiples templates {found.ids} -> saltado")
                continue
        if not prod and name:
            found = PRODUCT.search([('name', '=', name)])
            if len(found) == 1:
                prod = found[0]
            elif len(found) > 1:
                skipped_multi += 1
                logs.append(f"[{r}] NAME='{name}' múltiples templates {found.ids} -> saltado")
                continue

        # --- Valores comunes (create/write) ---
        vals = {}

        if name:
            vals['name'] = name

        # Categoría (crea si no existe)
        categ_path = _getv(row, 'categ_path')
        if categ_path:
            categ = _get_or_create_categ_by_path(categ_path)
            if categ:
                vals['categ_id'] = categ.id

        # Precios
        lp = _parse_number(_getv(row, 'list_price'))
        if lp is not None:
            vals['list_price'] = lp
        sp = _parse_number(_getv(row, 'standard_price'))
        if sp is not None:
            vals['standard_price'] = sp

        # CAByS como Many2one (cabys_product_id -> cabys.producto.code)
        cabys_val = _getv(row, 'cabys_code')
        cabys_val = str(cabys_val).strip() if cabys_val is not None else ''
        if has_cabys_m2o and cabys_val:
            cabys_rec = CABYS_PRODUCT.with_context(active_test=False).search([('codigo', '=', cabys_val)], limit=1)
            if cabys_rec:
                vals['cabys_product_id'] = cabys_rec.id
            else:
                logs.append(f"[{r}] CAByS '{cabys_val}' no encontrado en cabys.producto -> no se asigna")

        # Flags
        if 'purchase_ok' in idx:
            vals['purchase_ok'] = _parse_bool(_getv(row, 'purchase_ok'))
        if 'sale_ok' in idx:
            vals['sale_ok'] = _parse_bool(_getv(row, 'sale_ok'))

        # --- Crear o actualizar ---
        if prod:
            if ref:
                vals['default_code'] = ref
            prod.with_context(tracking_disable=True).write(vals)
            updated_total += 1
            print(f"[{r}] ✅ ACTUALIZADO ref={ref or '-'} name='{name}' -> {vals}")
        else:
            if ref:
                vals['default_code'] = ref
            vals.setdefault('type', 'consu')
            vals.setdefault('purchase_ok', True)
            vals.setdefault('sale_ok', True)
            prod = PRODUCT.create(vals)
            created_total += 1
            print(f"[{r}] 🆕 CREADO ref={ref or '-'} name='{name}' -> {vals}")

    except Exception as e:
        errores.append(f"[{r}] ❌ Error ref={ref or '-'} name='{name}' -> {e}")
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
ruta_errores = os.path.join(base_dir, 'errores_importacion.txt')
ruta_log = os.path.join(base_dir, 'import_log.txt')

if errores:
    with open(ruta_errores, 'w', encoding='utf-8') as f:
        f.write('\n'.join(errores))
    print(f"⚠️ {len(errores)} errores guardados en: {ruta_errores}")

with open(ruta_log, 'w', encoding='utf-8') as f:
    f.write('\n'.join(logs))
print(f"📝 Log de proceso en: {ruta_log}")

# ===== Resumen =====
print("=== RESUMEN ===")
print(f"Procesados: {procesados}")
print(f"Creados: {created_total}")
print(f"Actualizados: {updated_total}")
print(f"Saltados sin claves (nombre/ref): {skipped_no_keys}")
print(f"Saltados por múltiples coincidencias: {skipped_multi}")
print(f"Errores: {len(errores)}")
