# -*- coding: utf-8 -*-
# # Ejecutar en Odoo Shell:  odoo-bin shell -d <tu_db>
#
# import os
# import re
#
# import xlrd  # <-- usamos xlrd para leer .xls
#
# PARTNER = env['res.partner']
#
# # ===== Config =====
# NOMBRE_HOJA = 'Clientes'  # Cambia si tu hoja se llama distinto
# COMMIT_INTERVAL = 50      # commit cada N filas
# DEFAULT_XLS = 'clientes.xls'  # tu archivo .xls
#
#
# # ===== Utils =====
# def _normalize_header(s):
#     return re.sub(r'\s+', ' ', str(s or '').strip().lower())
#
#
# def _split_emails(raw):
#     """Recibe un string con correos separados por ; o , y devuelve lista limpia."""
#     if not raw:
#         return []
#     parts = re.split(r'[;,]', str(raw))
#     return [p.strip() for p in parts if p and p.strip()]
#
#
# def _resolve_path(filename):
#     """Devuelve ruta existente. Prioriza carpeta del script (__file__), luego CWD, luego carpeta padre."""
#     if os.path.isabs(filename):
#         if not os.path.exists(filename):
#             raise FileNotFoundError(f"No se encontró el archivo absoluto: {filename}")
#         return filename
#     tried = []
#     base_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
#     p1 = os.path.join(base_dir, filename); tried.append(p1)
#     p2 = os.path.join(os.getcwd(), filename); tried.append(p2)
#     p3 = os.path.join(os.path.dirname(base_dir), filename); tried.append(p3)
#     for p in tried:
#         if os.path.exists(p):
#             return p
#     raise FileNotFoundError("No se encontró el archivo '{0}'. Probé:\n- {1}".format(filename, "\n- ".join(tried)))
#
#
# def _find_field(model, candidates):
#     fields = env[model]._fields
#     for c in candidates:
#         if c in fields:
#             return c
#     return None
#
#
# def _normalize_code(val):
#     """Normaliza códigos que pueden venir como 1, '01', 1.0, '1.0', '01.0', etc."""
#     if val is None:
#         return ''
#     s = str(val).strip()
#     if not s:
#         return ''
#     # Si es puramente numérico (con posible .0)
#     if re.match(r'^\d+(\.0+)?$', s):
#         n = int(float(s))
#         return str(n)  # '01' -> '1', '1.0' -> '1'
#     return s
#
#
# def _safe_ref(xmlid):
#     """Referencia segura a registros por XMLID."""
#     try:
#         return env.ref(xmlid)
#     except ValueError:
#         return False
#
#
# def _getv(row_index, key):
#     """Obtiene el valor crudo de la celda según el alias de header_map."""
#     col = idx.get(key, None)
#     if col is None:
#         return None
#     try:
#         return sheet.cell_value(row_index, col)
#     except IndexError:
#         return None
#
#
# def _get_str(row_index, key):
#     """Devuelve el valor como string limpiado (o cadena vacía)."""
#     v = _getv(row_index, key)
#     if v is None:
#         return ''
#     return str(v).strip()
#
#
# # ===== Opcional: tipos de identificación CR (si el módulo existe) =====
# id_type_map = {
#     '01': _safe_ref("cr_electronic_invoice.Identificationtype_01"),  # FÍSICA
#     '02': _safe_ref("cr_electronic_invoice.Identificationtype_02"),  # JURÍDICA
#     '03': _safe_ref("cr_electronic_invoice.Identificationtype_03"),  # DIMEX
#     '04': _safe_ref("cr_electronic_invoice.Identificationtype_04"),  # NITE
#     '10': _safe_ref("cr_electronic_invoice.Identificationtype_06"),  # NO CONTRIBUYENTE (si existe)
# }
# id_type_field = _find_field('res.partner', ['identification_id', 'l10n_latam_identification_type_id'])
#
# country_cr = _safe_ref("base.cr")  # Costa Rica
#
# # ===== Input archivo =====
# ARCHIVO_IN = input(f"📄 Nombre del XLS (enter = {DEFAULT_XLS}): ").strip() or DEFAULT_XLS
# ARCHIVO = _resolve_path(ARCHIVO_IN)
# print(f"📂 Usando archivo: {ARCHIVO}")
#
# # ¿Importar como cliente, proveedor o ambos?
# tipo_entidad = input("👤 ¿Deseas importar como 1=Cliente, 2=Proveedor, 3=Ambos? (enter=1): ").strip() or '1'
# if tipo_entidad not in {'1', '2', '3'}:
#     raise ValueError("Solo puedes ingresar 1 (cliente), 2 (proveedor) o 3 (ambos).")
#
# es_cliente = tipo_entidad in {'1', '3'}
# es_proveedor = tipo_entidad in {'2', '3'}
#
# # ===== Cargar libro / hoja .XLS con xlrd =====
# book = xlrd.open_workbook(ARCHIVO)
# sheet = None
# for sh in book.sheets():
#     if sh.name == NOMBRE_HOJA:
#         sheet = sh
#         break
# if sheet is None:
#     raise ValueError(f"La hoja '{NOMBRE_HOJA}' no existe. Hojas: {[sh.name for sh in book.sheets()]}")
#
# # Leer encabezados
# headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
# norm_headers = [_normalize_header(h) for h in headers]
#
# # Mapeo de columnas
# header_map = {
#     'cod_clie': 'client_code',
#     'nombre': 'name',
#     'cedula': 'vat',
#     'tipo_cedula': 'id_type',
#     'pais': 'country_code',
#
#     'telefono': 'phone',
#     'telefono_2': 'mobile',
#     'direccion': 'street',
#
#     # Ubicación
#     'cod_prov': 'prov',
#     'cod_cant': 'cant',
#     'cod_dist': 'dist',
#
#     # Términos de pago (plazo)
#     'plazo': 'plazo',
#
#     # Correos
#     'e_mail': 'email_1',
#     'e_mail_cortesia': 'email_courtesy',
#     'correo2': 'email_2',
#     'correo3': 'email_3',
#
#     # Notas
#     'notas1': 'note_1',
#     'notas2': 'note_2',
#     'notas3': 'note_3',
#     'notas5': 'note_5',
#
#     'cod_vend': 'salesperson_code',
#     'cod_ruta': 'route_code',
# }
#
# idx = {}
# for i, h in enumerate(norm_headers):
#     print('>>', i, h)
#     if h in header_map:
#         idx[header_map[h]] = i
#
#
# # ===== Procesamiento =====
# errores = []
# logs = []
# procesados = 0
# created_total = 0
# updated_total = 0
# skipped_no_keys = 0
# skipped_multi = 0
# commit_counter = 0
#
# for r in range(1, sheet.nrows):  # desde fila 2 (índice 1)
#     procesados += 1
#     try:
#         # ===== Lectura de datos base =====
#         client_code = _get_str(r, 'client_code')
#         name = _get_str(r, 'name')
#         vat = _get_str(r, 'vat')
#         id_type_code = _get_str(r, 'id_type')
#
#         phone = _get_str(r, 'phone')
#         mobile = _get_str(r, 'mobile')
#         street = _get_str(r, 'street')
#         plazo_raw = _getv(r, 'plazo')
#         plazo = ''
#         if plazo_raw is not None:
#             # Si viene como número (int/float) desde Excel
#             if isinstance(plazo_raw, (int, float)):
#                 plazo = str(int(plazo_raw))
#             else:
#                 s = str(plazo_raw).strip()
#                 # Si es algo tipo "60.0" o "60.00" lo dejamos como "60"
#                 m = re.match(r'^(\d+)(\.0+)?$', s)
#                 plazo = m.group(1) if m else s
#
#         prov_code = _normalize_code(_getv(r, 'prov'))
#         cant_code = _normalize_code(_getv(r, 'cant'))
#         dist_code = _normalize_code(_getv(r, 'dist'))
#
#         # Si no hay claves mínimas, saltar
#         if not client_code and not name and not vat:
#             skipped_no_keys += 1
#             logs.append(f"[{r + 1}] sin COD_CLIE, NOMBRE ni CEDULA -> saltado")
#             continue
#
#         # ===== Buscar partner existente por client_code =====
#         partner = False
#         if client_code:
#             found = PARTNER.search([('client_code', '=', client_code)])
#             if len(found) == 1:
#                 partner = found[0]
#             elif len(found) > 1:
#                 skipped_multi += 1
#                 logs.append(f"[{r + 1}] client_code={client_code} múltiples partners {found.ids} -> saltado")
#                 continue
#
#         # ===== Construcción de vals =====
#         vals = {}
#
#         if name:
#             vals['name'] = name
#         if client_code:
#             vals['client_code'] = client_code
#         if vat:
#             vals['vat'] = vat
#         if phone:
#             vals['phone'] = phone
#         if mobile:
#             vals['mobile'] = mobile
#         if street:
#             vals['street'] = street
#
#
#         cod_venta = _get_str(r, 'salesperson_code')
#
#         # if cod_venta == '0010':
#         #     vals['user_id'] = vat
#         if cod_venta == '0012':
#             vals['user_id'] = 25
#         if cod_venta == '0013':
#             vals['user_id'] = 23
#         if cod_venta == '0014':
#             vals['user_id'] = 19
#         if cod_venta == '0015':
#             vals['user_id'] = 24
#         # if cod_venta == '0016':
#         #     vals['user_id'] = 19
#         # if cod_venta == '0019':
#         #     vals['user_id'] = vat
#         if cod_venta == '0020':
#             vals['user_id'] = 26
#         if cod_venta == '0022':
#             vals['user_id'] = 27
#
#         # cod_ruta = _get_str(r, 'route_code')
#         #
#         # if cod_ruta == '0000':
#         #     vals['user_id'] = vat
#         # if cod_ruta == '0010':
#         #     vals['user_id'] = 25
#         # if cod_ruta == '0030':
#         #     vals['user_id'] = 23
#         # if cod_ruta == '0040':
#         #     vals['user_id'] = 19
#         # if cod_ruta == '0050':
#         #     vals['user_id'] = 24
#         # if cod_ruta == '0060':
#         #     vals['user_id'] = 19
#         # if cod_ruta == '0070':
#         #     vals['user_id'] = vat
#         # if cod_ruta == '0080':
#         #     vals['user_id'] = 26
#         # if cod_ruta == '0090':
#         #     vals['user_id'] = 27
#         # if cod_ruta == '0100':
#         #     vals['user_id'] = vat
#         # if cod_ruta == '0120':
#         #     vals['user_id'] = 26
#         # if cod_ruta == '0130':
#         #     vals['user_id'] = 27
#
#
#
#         # Términos de pago (plazo -> account.payment.term)
#         if plazo:
#             term = env['account.payment.term'].search([('name', 'ilike', plazo)], limit=1)
#             if term:
#                 vals['property_payment_term_id'] = term.id
#             else:
#                 print(f"[{r + 1}] ⚠ No se encontró account.payment.term con nombre similar a '{plazo}'")
#         else:
#             vals['property_payment_term_id'] = False
#
#         # ===== Ubicación: provincia (state), cantón (county), distrito (district) =====
#         if country_cr:
#             if prov_code:
#                 prov_candidates = {prov_code, prov_code.zfill(2)}
#                 domain_state = [
#                     ('code', 'in', list(prov_candidates)),
#                     ('country_id', '=', country_cr.id),
#                 ]
#                 state = env['res.country.state'].search(domain_state, limit=1)
#                 if not state:
#                     print(f"[{r + 1}] ⚠ No se encontró provincia (res.country.state) con code={prov_code} para país CR")
#                 else:
#                     vals['state_id'] = state.id
#
#                     # Cantón
#                     if cant_code:
#                         cant_candidates = {cant_code, cant_code.zfill(2)}
#                         county = env['res.country.county'].search([
#                             ('code', 'in', list(cant_candidates)),
#                             ('state_id', '=', state.id),
#                         ], limit=1)
#                         if not county:
#                             print(
#                                 f"[{r + 1}] ⚠ No se encontró cantón (res.country.county) code={cant_code} "
#                                 f"para provincia {state.code} (CR)"
#                             )
#                         else:
#                             vals['county_id'] = county.id
#
#                             # Distrito
#                             if dist_code:
#                                 dist_candidates = {dist_code, dist_code.zfill(2)}
#                                 district = env['res.country.district'].search([
#                                     ('code', 'in', list(dist_candidates)),
#                                     ('county_id', '=', county.id),
#                                 ], limit=1)
#                                 if not district:
#                                     print(
#                                         f"[{r + 1}] ⚠ No se encontró distrito (res.country.district) code={dist_code} "
#                                         f"para cantón {county.code} (CR)"
#                                     )
#                                 else:
#                                     vals['district_id'] = district.id
#             else:
#                 if cant_code or dist_code:
#                     print(
#                         f"[{r + 1}] ⚠ Hay cantón/distrito (cod_cant={cant_code}, cod_dist={dist_code}) "
#                         f"pero falta cod_prov -> no se puede localizar jerarquía completa (CR)."
#                     )
#         else:
#             if prov_code or cant_code or dist_code:
#                 print(
#                     f"[{r + 1}] ⚠ Se encontraron códigos de ubicación "
#                     f"(cod_prov={prov_code}, cod_cant={cant_code}, cod_dist={dist_code}) "
#                     f"pero no existe país CR (base.cr) en la base de datos."
#                 )
#
#         # ===== Correos: e_mail, e_mail_cortesia, correo2, correo3 =====
#         email_1 = _getv(r, 'email_1')
#         email_courtesy = _getv(r, 'email_courtesy')
#         email_2 = _getv(r, 'email_2')
#         email_3 = _getv(r, 'email_3')
#
#         all_email_raw = [email_1, email_courtesy, email_2, email_3]
#
#         unique_emails = []
#         seen = set()
#         for raw in all_email_raw:
#             for e in _split_emails(raw):
#                 key = e.strip()
#                 if key and key not in seen:
#                     seen.add(key)
#                     unique_emails.append(e)
#
#         if unique_emails:
#             vals['email'] = ';'.join(unique_emails)
#
#         # ===== Notas: notas1, notas2, notas3, notas5 -> comment (sobrescribe) =====
#         note_1 = _getv(r, 'note_1')
#         note_2 = _getv(r, 'note_2')
#         note_3 = _getv(r, 'note_3')
#         note_5 = _getv(r, 'note_5')
#
#         notes_parts = []
#         for n in (note_1, note_2, note_3, note_5):
#             if n:
#                 txt = str(n).strip()
#                 if txt:
#                     notes_parts.append(txt)
#
#         if notes_parts:
#             vals['comment'] = '\n'.join(notes_parts)
#         else:
#             # Limpia el comentario si no hay notas en el Excel
#             vals['comment'] = False
#
#         # ===== Cliente / proveedor =====
#         current_customer_rank = partner.customer_rank if partner else 0
#         current_supplier_rank = partner.supplier_rank if partner else 0
#         if es_cliente:
#             vals['customer_rank'] = max(1, current_customer_rank or 0)
#         if es_proveedor:
#             vals['supplier_rank'] = max(1, current_supplier_rank or 0)
#
#         # ===== Tipo de persona y tipo de identificación =====
#         if id_type_code in id_type_map and id_type_map[id_type_code]:
#             if id_type_field:
#                 vals[id_type_field] = id_type_map[id_type_code].id
#
#             if id_type_code in ('01', '1'):
#                 vals['company_type'] = 'person'
#                 vals['is_company'] = False
#             else:
#                 vals['company_type'] = 'company'
#                 vals['is_company'] = True
#
#         # País: fija CR
#         if country_cr:
#             vals['country_id'] = country_cr.id
#
#         # ===== Crear / actualizar =====
#         if partner:
#             partner.with_context(tracking_disable=True).write(vals)
#             updated_total += 1
#             print(f"[{r + 1}] ✅ ACTUALIZADO client_code={client_code or '-'} name='{name}' -> {vals}")
#         else:
#             if 'company_type' not in vals:
#                 vals.setdefault('company_type', 'company')
#                 vals.setdefault('is_company', True)
#             partner = PARTNER.create(vals)
#             created_total += 1
#             print(f"[{r + 1}] 🆕 CREADO client_code={client_code or '-'} name='{name}' -> {vals}")
#
#     except Exception as e:
#         errores.append(f"[{r + 1}] ❌ Error client_code={client_code or '-'} name='{name}' -> {e}")
#         print(errores[-1])
#
#     # Commits por lotes
#     commit_counter += 1
#     if commit_counter >= COMMIT_INTERVAL:
#         env.cr.commit()
#         commit_counter = 0
#
# # Commit final
# if commit_counter > 0:
#     env.cr.commit()
#
# # ===== Logs / Errores =====
# base_dir = os.getcwd()
# ruta_errores = os.path.join(base_dir, 'errores_importacion_clientes.txt')
# ruta_log = os.path.join(base_dir, 'import_clientes_log.txt')
#
# if errores:
#     with open(ruta_errores, 'w', encoding='utf-8') as f:
#         f.write('\n'.join(errores))
#     print(f"⚠️ {len(errores)} errores guardados en: {ruta_errores}")
#
# with open(ruta_log, 'w', encoding='utf-8') as f:
#     f.write('\n'.join(logs))
# print(f"📝 Log de proceso en: {ruta_log}")
#
# # ===== Resumen =====
# print("=== RESUMEN CLIENTES ===")
# print(f"Procesados: {procesados}")
# print(f"Creados: {created_total}")
# print(f"Actualizados: {updated_total}")
# print(f"Saltados sin claves (COD_CLIE/NOMBRE/CEDULA): {skipped_no_keys}")
# print(f"Saltados por múltiples coincidencias: {skipped_multi}")
# print(f"Errores: {len(errores)}")


import time

PARTNER = env['res.partner']

# Busca todos los contactos (ajusta el dominio si quieres filtrar)
partners = PARTNER.search([])
total = len(partners)
print(f"Se encontraron {total} contactos.")

for idx, partner in enumerate(partners, start=1):
    try:
        print(f"[{idx}/{total}] Ejecutando action_get_economic_activities en partner ID {partner.id} - {partner.display_name}")
        partner.action_get_economic_activities()
        env.cr.commit()  # Guarda cambios por cada contacto
        print(f"[{idx}/{total}] ✅ OK")
    except Exception as e:
        env.cr.rollback()
        print(f"[{idx}/{total}] ❌ Error en partner ID {partner.id}: {e}")

    # Esperar al menos 5 segundos antes del siguiente
    time.sleep(2)

print("Proceso terminado.")