# reports/inventory_balance_xlsx.py
# -*- coding: utf-8 -*-

from odoo import models, fields


class InventoryBalanceXlsx(models.AbstractModel):
    _name = "report.inventory_balance_wizard.inventory_balance_xlsx"
    _inherit = "report.report_xlsx.abstract"

    # -----------------------------
    # Helpers
    # -----------------------------
    def _get_report_currencies(self, wiz):
        company = wiz.env.company
        company_currency = company.currency_id

        pricelist_currencies = wiz.env["product.pricelist"].search([
            ("active", "=", True),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ]).mapped("currency_id")

        currencies = [company_currency]
        for c in pricelist_currencies:
            if c and c not in currencies:
                currencies.append(c)
        return currencies

    def _dt_to_datetime(self, wiz, dt_val):
        """read_group puede devolver datetime o string; normalizamos a datetime."""
        if not dt_val:
            return False
        if isinstance(dt_val, str):
            # Odoo suele devolver string en algunos contextos
            return fields.Datetime.from_string(dt_val)
        return dt_val

    def _get_bucket_locations(self, wiz):
        """
        "Bucket" = ubicaciones principales a mostrar en Excel (columna Ubicación):
        - Si el wizard tiene location_ids: esas
        - Si no: la ubicación principal del almacén (lot_stock_id)
        """
        if wiz.location_ids:
            buckets = wiz.location_ids
        elif wiz.warehouse_id and wiz.warehouse_id.lot_stock_id:
            buckets = wiz.warehouse_id.lot_stock_id
        else:
            buckets = wiz.env["stock.location"]
        return buckets

    def _build_loc_to_bucket_map(self, wiz, effective_location_ids, bucket_locations):
        """
        Mapea cualquier ubicación (incluyendo sub-ubicaciones) al "bucket" más cercano
        dentro de bucket_locations. Así evitamos el problema:
          quant.location_id = WH/Bodega/Stock
          move_line.location_dest_id = WH/Bodega
        y no coincidían.

        Retorna dict: loc_id -> bucket_id (o False si no cae en ningún bucket)
        """
        StockLocation = wiz.env["stock.location"].sudo()

        bucket_ids = set(bucket_locations.ids)
        if not bucket_ids:
            return {}

        # Traemos parent_path de todas las ubicaciones efectivas
        locs = StockLocation.browse(list(set(effective_location_ids))).read(["id", "parent_path", "display_name"])
        bucket_locs = StockLocation.browse(list(bucket_ids)).read(["id", "parent_path"])

        # Prepara lookup: bucket_id -> set(ancestors ids) usando parent_path
        bucket_ancestor_sets = {}
        for b in bucket_locs:
            # parent_path es tipo "/1/2/3/"
            path = b.get("parent_path") or ""
            anc = [int(x) for x in path.split("/") if x.isdigit()]
            anc.append(b["id"])  # incluirse
            bucket_ancestor_sets[b["id"]] = set(anc)

        # Para elegir el bucket "más cercano": usamos el bucket con mayor profundidad
        # (más largo el parent_path) que sea ancestro de la ubicación.
        bucket_depth = {}
        for b in bucket_locs:
            path = b.get("parent_path") or ""
            depth = len([x for x in path.split("/") if x.isdigit()])
            bucket_depth[b["id"]] = depth

        loc_to_bucket = {}
        for l in locs:
            lid = l["id"]
            path = l.get("parent_path") or ""
            anc = [int(x) for x in path.split("/") if x.isdigit()]
            anc.append(lid)
            anc_set = set(anc)

            candidates = []
            for bid, b_anc in bucket_ancestor_sets.items():
                # si el bucket está en ancestros de la ubicación => el bucket es ancestro
                if bid in anc_set:
                    candidates.append(bid)

            if not candidates:
                loc_to_bucket[lid] = False
                continue

            # el más profundo = más específico
            best = sorted(candidates, key=lambda x: bucket_depth.get(x, 0), reverse=True)[0]
            loc_to_bucket[lid] = best

        return loc_to_bucket

    def _build_first_in_last_out_maps(self, wiz, effective_location_ids, loc_to_bucket):
        """
        Devuelve 2 dicts:
          - first_in_map[(product_id, bucket_id)] = first_in_dt
          - last_out_map[(product_id, bucket_id)] = last_out_dt

        Reglas:
          - Ingreso: move_line.location_dest_id dentro de ubicaciones efectivas (done)
          - Salida:  move_line.location_id dentro de ubicaciones efectivas (done)
          - Cualquier tipo de operación (compras/ventas/internas/devoluciones) queda cubierto.
        """
        MoveLine = wiz.env["stock.move.line"].sudo()

        # -------- Ingreso (min date) por (product, exact_dest_loc) --------
        in_domain = [
            ("state", "=", "done"),
            ("product_id", "!=", False),
            ("location_dest_id", "in", effective_location_ids),
        ]
        in_groups = MoveLine.read_group(
            in_domain,
            ["product_id", "location_dest_id", "date:min"],
            ["product_id", "location_dest_id"],
            lazy=False,
        )

        first_in_map = {}
        for g in in_groups:
            prod = g.get("product_id") and g["product_id"][0]
            loc = g.get("location_dest_id") and g["location_dest_id"][0]
            if not prod or not loc:
                continue
            bucket = loc_to_bucket.get(loc)
            if not bucket:
                continue
            dt_min = self._dt_to_datetime(wiz, g.get("date_min"))
            if not dt_min:
                continue

            key = (prod, bucket)
            prev = first_in_map.get(key)
            if not prev or dt_min < prev:
                first_in_map[key] = dt_min

        # -------- Salida (max date) por (product, exact_source_loc) --------
        out_domain = [
            ("state", "=", "done"),
            ("product_id", "!=", False),
            ("location_id", "in", effective_location_ids),
        ]
        out_groups = MoveLine.read_group(
            out_domain,
            ["product_id", "location_id", "date:max"],
            ["product_id", "location_id"],
            lazy=False,
        )

        last_out_map = {}
        for g in out_groups:
            prod = g.get("product_id") and g["product_id"][0]
            loc = g.get("location_id") and g["location_id"][0]
            if not prod or not loc:
                continue
            bucket = loc_to_bucket.get(loc)
            if not bucket:
                continue
            dt_max = self._dt_to_datetime(wiz, g.get("date_max"))
            if not dt_max:
                continue

            key = (prod, bucket)
            prev = last_out_map.get(key)
            if not prev or dt_max > prev:
                last_out_map[key] = dt_max

        return first_in_map, last_out_map

    # -----------------------------
    # Report main
    # -----------------------------
    def generate_xlsx_report(self, workbook, data, wizards):
        for wiz in wizards:
            sheet = workbook.add_worksheet("Inventario")

            title_fmt = workbook.add_format({"bold": True, "font_size": 12})
            head_fmt = workbook.add_format({"bold": True, "border": 1})
            text_fmt = workbook.add_format({"border": 1})
            num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
            qty_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.####"})
            dt_fmt = workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd hh:mm"})

            company = wiz.env.company
            company_currency = company.currency_id
            today = fields.Date.context_today(wiz)

            currencies = self._get_report_currencies(wiz)

            # Ubicaciones efectivas (incluye child si el wizard lo decide)
            effective_location_ids = wiz._get_effective_locations()

            # Buckets a mostrar (ubicaciones seleccionadas o stock principal del almacén)
            bucket_locations = self._get_bucket_locations(wiz)

            # Mapa de loc -> bucket (para que sub-ubicaciones caigan en el bucket correcto)
            loc_to_bucket = self._build_loc_to_bucket_map(
                wiz,
                effective_location_ids=effective_location_ids,
                bucket_locations=bucket_locations,
            )

            # Fechas: primer ingreso y última salida por (producto, bucket)
            first_in_map, last_out_map = self._build_first_in_last_out_maps(
                wiz,
                effective_location_ids=effective_location_ids,
                loc_to_bucket=loc_to_bucket,
            )

            # Headers (solo lo que pediste)
            base_headers = [
                "Nombre del producto",
                "SKU",
                "Categoría",
                "Ubicación",
                "Cantidad a mano",
                "Primer ingreso",
                "Última salida",
                f"Costo ({company_currency.name})",
                f"Precio venta ({company_currency.name})",
                f"Valorizado ({company_currency.name})",
            ]
            extra_headers = []
            for c in currencies:
                if c != company_currency:
                    extra_headers.append(f"Valorizado ({c.name})")
            headers = base_headers + extra_headers

            # Encabezado / filtros
            sheet.write(0, 0, "Reporte de inventario", title_fmt)
            sheet.write(1, 0, "Filtros:", head_fmt)
            sheet.write(1, 1, f"Almacén: {wiz.warehouse_id.display_name or '-'}", text_fmt)
            sheet.write(2, 1, f"Ubicaciones: {', '.join(wiz.location_ids.mapped('display_name')) or '-'}", text_fmt)
            sheet.write(3, 1, f"Incluir sub-ubicaciones: {'Sí' if wiz.include_child_locations else 'No'}", text_fmt)
            sheet.write(4, 1, f"Solo stock > 0: {'Sí' if wiz.only_positive_qty else 'No'}", text_fmt)
            sheet.write(5, 1, f"Agrupar por ubicación: {'Sí' if wiz.group_by_location else 'No'}", text_fmt)

            # Header row
            row = 7
            for col, h in enumerate(headers):
                sheet.write(row, col, h, head_fmt)

            # Datos base desde quants
            domain = wiz._get_quant_domain()

            # Leemos agrupado por producto y (si aplica) por ubicación exacta del quant
            groupby = ["product_id"]
            read_fields = ["quantity:sum", "product_id"]
            if wiz.group_by_location:
                groupby.append("location_id")
                read_fields.append("location_id")

            quant_groups = wiz.env["stock.quant"].sudo().read_group(
                domain,
                read_fields,
                groupby,
                lazy=False,
            )

            # Si agrupas por ubicación, vamos a reagrupar por bucket (para que cuadre con fechas)
            # Si NO agrupas por ubicación, el bucket será "scope" del wizard (pueden ser varias)
            aggregated = {}

            if wiz.group_by_location:
                # (product, bucket) -> qty_sum
                for g in quant_groups:
                    product_id = g.get("product_id") and g["product_id"][0]
                    loc_id = g.get("location_id") and g["location_id"][0]
                    if not product_id or not loc_id:
                        continue
                    bucket_id = loc_to_bucket.get(loc_id)
                    if not bucket_id:
                        continue
                    key = (product_id, bucket_id)
                    aggregated[key] = aggregated.get(key, 0.0) + (g.get("quantity", 0.0) or 0.0)
            else:
                # No agrupado por ubicación: un solo “bucket” lógico para la fila.
                # Si hay múltiples buckets (varias location_ids), usamos bucket_id = 0 y etiqueta lista.
                for g in quant_groups:
                    product_id = g.get("product_id") and g["product_id"][0]
                    if not product_id:
                        continue
                    key = (product_id, 0)
                    aggregated[key] = aggregated.get(key, 0.0) + (g.get("quantity", 0.0) or 0.0)

            # Etiqueta de ubicación cuando NO agrupas por ubicación
            if wiz.location_ids:
                locations_label = ", ".join(wiz.location_ids.mapped("display_name"))
            elif wiz.warehouse_id and wiz.warehouse_id.lot_stock_id:
                locations_label = wiz.warehouse_id.lot_stock_id.display_name
            else:
                locations_label = "-"

            # Para nombre de bucket cuando agrupas
            bucket_name_by_id = {b.id: b.display_name for b in bucket_locations}

            def _write_dt(r, c, dt_val):
                if not dt_val:
                    sheet.write(r, c, "", text_fmt)
                    return
                dt_val = self._dt_to_datetime(wiz, dt_val)
                if not dt_val:
                    sheet.write(r, c, "", text_fmt)
                    return
                dt_local = fields.Datetime.context_timestamp(wiz, dt_val)
                sheet.write_datetime(r, c, dt_local.replace(tzinfo=None), dt_fmt)

            # Escribir filas
            row += 1
            Product = wiz.env["product.product"].sudo()

            # Orden estable por nombre
            sorted_keys = sorted(
                aggregated.keys(),
                key=lambda k: (Product.browse(k[0]).display_name or "", k[1] or 0)
            )

            for (product_id, bucket_id), qty in [(k, aggregated[k]) for k in sorted_keys]:
                product = Product.browse(product_id)

                name = product.display_name or ""
                sku = product.default_code or ""
                categ = product.categ_id.complete_name or ""

                if wiz.group_by_location:
                    loc_name = bucket_name_by_id.get(bucket_id, "-")
                    first_in = first_in_map.get((product_id, bucket_id))
                    last_out = last_out_map.get((product_id, bucket_id))
                else:
                    # Consolidado: primer ingreso = mínimo entre buckets; última salida = máximo entre buckets
                    loc_name = locations_label

                    # Si hay buckets definidos, agregamos de todos los buckets:
                    if bucket_locations:
                        all_in = []
                        all_out = []
                        for bid in bucket_locations.ids:
                            dt_in = first_in_map.get((product_id, bid))
                            if dt_in:
                                all_in.append(dt_in)
                            dt_out = last_out_map.get((product_id, bid))
                            if dt_out:
                                all_out.append(dt_out)
                        first_in = min(all_in) if all_in else False
                        last_out = max(all_out) if all_out else False
                    else:
                        first_in = False
                        last_out = False

                cost = product.standard_price or 0.0
                sale = product.list_price or 0.0
                valued_company = qty * cost

                col = 0
                sheet.write(row, col, name, text_fmt);
                col += 1
                sheet.write(row, col, sku, text_fmt);
                col += 1
                sheet.write(row, col, categ, text_fmt);
                col += 1
                sheet.write(row, col, loc_name or "-", text_fmt);
                col += 1
                sheet.write_number(row, col, qty, qty_fmt);
                col += 1

                _write_dt(row, col, first_in);
                col += 1
                _write_dt(row, col, last_out);
                col += 1

                sheet.write_number(row, col, cost, num_fmt);
                col += 1
                sheet.write_number(row, col, sale, num_fmt);
                col += 1
                sheet.write_number(row, col, valued_company, num_fmt);
                col += 1

                for ccy in currencies:
                    if ccy == company_currency:
                        continue
                    valued_other = company_currency._convert(valued_company, ccy, company, today)
                    sheet.write_number(row, col, valued_other, num_fmt)
                    col += 1

                row += 1

            # Anchos
            col_widths = [
                             28, 12, 24, 28, 14, 18, 18, 14, 16, 18
                         ] + [18 for _ in extra_headers]
            for i, w in enumerate(col_widths):
                sheet.set_column(i, i, w)


# reports/inventory_balance_xlsx.py
# -*- coding: utf-8 -*-

from odoo import models, fields


class InventoryBalanceXlsx(models.AbstractModel):
    _name = "report.inventory_balance_wizard.inventory_balance_xlsx"
    _inherit = "report.report_xlsx.abstract"

    # -----------------------------
    # Helpers
    # -----------------------------
    def _get_report_currencies(self, wiz):
        company = wiz.env.company
        company_currency = company.currency_id

        pricelist_currencies = wiz.env["product.pricelist"].search([
            ("active", "=", True),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ]).mapped("currency_id")

        currencies = [company_currency]
        for c in pricelist_currencies:
            if c and c not in currencies:
                currencies.append(c)
        return currencies

    def _dt_to_datetime(self, wiz, dt_val):
        """read_group puede devolver datetime o string; normalizamos a datetime."""
        if not dt_val:
            return False
        if isinstance(dt_val, str):
            # Odoo suele devolver string en algunos contextos
            return fields.Datetime.from_string(dt_val)
        return dt_val

    def _get_bucket_locations(self, wiz):
        """
        "Bucket" = ubicaciones principales a mostrar en Excel (columna Ubicación):
        - Si el wizard tiene location_ids: esas
        - Si no: la ubicación principal del almacén (lot_stock_id)
        """
        if wiz.location_ids:
            buckets = wiz.location_ids
        elif wiz.warehouse_id and wiz.warehouse_id.lot_stock_id:
            buckets = wiz.warehouse_id.lot_stock_id
        else:
            buckets = wiz.env["stock.location"]
        return buckets

    def _build_loc_to_bucket_map(self, wiz, effective_location_ids, bucket_locations):
        """
        Mapea cualquier ubicación (incluyendo sub-ubicaciones) al "bucket" más cercano
        dentro de bucket_locations. Así evitamos el problema:
          quant.location_id = WH/Bodega/Stock
          move_line.location_dest_id = WH/Bodega
        y no coincidían.

        Retorna dict: loc_id -> bucket_id (o False si no cae en ningún bucket)
        """
        StockLocation = wiz.env["stock.location"].sudo()

        bucket_ids = set(bucket_locations.ids)
        if not bucket_ids:
            return {}

        # Traemos parent_path de todas las ubicaciones efectivas
        locs = StockLocation.browse(list(set(effective_location_ids))).read(["id", "parent_path", "display_name"])
        bucket_locs = StockLocation.browse(list(bucket_ids)).read(["id", "parent_path"])

        # Prepara lookup: bucket_id -> set(ancestors ids) usando parent_path
        bucket_ancestor_sets = {}
        for b in bucket_locs:
            # parent_path es tipo "/1/2/3/"
            path = b.get("parent_path") or ""
            anc = [int(x) for x in path.split("/") if x.isdigit()]
            anc.append(b["id"])  # incluirse
            bucket_ancestor_sets[b["id"]] = set(anc)

        # Para elegir el bucket "más cercano": usamos el bucket con mayor profundidad
        # (más largo el parent_path) que sea ancestro de la ubicación.
        bucket_depth = {}
        for b in bucket_locs:
            path = b.get("parent_path") or ""
            depth = len([x for x in path.split("/") if x.isdigit()])
            bucket_depth[b["id"]] = depth

        loc_to_bucket = {}
        for l in locs:
            lid = l["id"]
            path = l.get("parent_path") or ""
            anc = [int(x) for x in path.split("/") if x.isdigit()]
            anc.append(lid)
            anc_set = set(anc)

            candidates = []
            for bid, b_anc in bucket_ancestor_sets.items():
                # si el bucket está en ancestros de la ubicación => el bucket es ancestro
                if bid in anc_set:
                    candidates.append(bid)

            if not candidates:
                loc_to_bucket[lid] = False
                continue

            # el más profundo = más específico
            best = sorted(candidates, key=lambda x: bucket_depth.get(x, 0), reverse=True)[0]
            loc_to_bucket[lid] = best

        return loc_to_bucket

    def _build_first_in_last_out_maps(self, wiz, effective_location_ids, loc_to_bucket):
        """
        Devuelve 2 dicts:
          - first_in_map[(product_id, bucket_id)] = first_in_dt
          - last_out_map[(product_id, bucket_id)] = last_out_dt

        Reglas:
          - Ingreso: move_line.location_dest_id dentro de ubicaciones efectivas (done)
          - Salida:  move_line.location_id dentro de ubicaciones efectivas (done)
          - Cualquier tipo de operación (compras/ventas/internas/devoluciones) queda cubierto.
        """
        MoveLine = wiz.env["stock.move.line"].sudo()

        # -------- Ingreso (min date) por (product, exact_dest_loc) --------
        in_domain = [
            ("state", "=", "done"),
            ("product_id", "!=", False),
            ("location_dest_id", "in", effective_location_ids),
        ]
        in_groups = MoveLine.read_group(
            in_domain,
            ["product_id", "location_dest_id", "date:min"],
            ["product_id", "location_dest_id"],
            lazy=False,
        )

        first_in_map = {}
        for g in in_groups:
            prod = g.get("product_id") and g["product_id"][0]
            loc = g.get("location_dest_id") and g["location_dest_id"][0]
            if not prod or not loc:
                continue
            bucket = loc_to_bucket.get(loc)
            if not bucket:
                continue
            dt_min = self._dt_to_datetime(wiz, g.get("date_min"))
            if not dt_min:
                continue

            key = (prod, bucket)
            prev = first_in_map.get(key)
            if not prev or dt_min < prev:
                first_in_map[key] = dt_min

        # -------- Salida (max date) por (product, exact_source_loc) --------
        out_domain = [
            ("state", "=", "done"),
            ("product_id", "!=", False),
            ("location_id", "in", effective_location_ids),
        ]
        out_groups = MoveLine.read_group(
            out_domain,
            ["product_id", "location_id", "date:max"],
            ["product_id", "location_id"],
            lazy=False,
        )

        last_out_map = {}
        for g in out_groups:
            prod = g.get("product_id") and g["product_id"][0]
            loc = g.get("location_id") and g["location_id"][0]
            if not prod or not loc:
                continue
            bucket = loc_to_bucket.get(loc)
            if not bucket:
                continue
            dt_max = self._dt_to_datetime(wiz, g.get("date_max"))
            if not dt_max:
                continue

            key = (prod, bucket)
            prev = last_out_map.get(key)
            if not prev or dt_max > prev:
                last_out_map[key] = dt_max

        return first_in_map, last_out_map

    # -----------------------------
    # Report main
    # -----------------------------
    def generate_xlsx_report(self, workbook, data, wizards):
        for wiz in wizards:
            sheet = workbook.add_worksheet("Inventario")

            title_fmt = workbook.add_format({"bold": True, "font_size": 12})
            head_fmt = workbook.add_format({"bold": True, "border": 1})
            text_fmt = workbook.add_format({"border": 1})
            num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
            qty_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.####"})
            dt_fmt = workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd hh:mm"})

            company = wiz.env.company
            company_currency = company.currency_id
            today = fields.Date.context_today(wiz)

            currencies = self._get_report_currencies(wiz)

            # Ubicaciones efectivas (incluye child si el wizard lo decide)
            effective_location_ids = wiz._get_effective_locations()

            # Buckets a mostrar (ubicaciones seleccionadas o stock principal del almacén)
            bucket_locations = self._get_bucket_locations(wiz)

            # Mapa de loc -> bucket (para que sub-ubicaciones caigan en el bucket correcto)
            loc_to_bucket = self._build_loc_to_bucket_map(
                wiz,
                effective_location_ids=effective_location_ids,
                bucket_locations=bucket_locations,
            )

            # Fechas: primer ingreso y última salida por (producto, bucket)
            first_in_map, last_out_map = self._build_first_in_last_out_maps(
                wiz,
                effective_location_ids=effective_location_ids,
                loc_to_bucket=loc_to_bucket,
            )

            # Headers (solo lo que pediste)
            base_headers = [
                "Nombre del producto",
                "SKU",
                "Categoría",
                "Ubicación",
                "Cantidad a mano",
                "Primer ingreso",
                "Última salida",
                f"Costo ({company_currency.name})",
                f"Precio venta ({company_currency.name})",
                f"Valorizado ({company_currency.name})",
            ]
            extra_headers = []
            for c in currencies:
                if c != company_currency:
                    extra_headers.append(f"Valorizado ({c.name})")
            headers = base_headers + extra_headers

            # Encabezado / filtros
            sheet.write(0, 0, "Reporte de inventario", title_fmt)
            sheet.write(1, 0, "Filtros:", head_fmt)
            sheet.write(1, 1, f"Almacén: {wiz.warehouse_id.display_name or '-'}", text_fmt)
            sheet.write(2, 1, f"Ubicaciones: {', '.join(wiz.location_ids.mapped('display_name')) or '-'}", text_fmt)
            sheet.write(3, 1, f"Incluir sub-ubicaciones: {'Sí' if wiz.include_child_locations else 'No'}", text_fmt)
            sheet.write(4, 1, f"Solo stock > 0: {'Sí' if wiz.only_positive_qty else 'No'}", text_fmt)
            sheet.write(5, 1, f"Agrupar por ubicación: {'Sí' if wiz.group_by_location else 'No'}", text_fmt)

            # Header row
            row = 7
            for col, h in enumerate(headers):
                sheet.write(row, col, h, head_fmt)

            # Datos base desde quants
            domain = wiz._get_quant_domain()

            # Leemos agrupado por producto y (si aplica) por ubicación exacta del quant
            groupby = ["product_id"]
            read_fields = ["quantity:sum", "product_id"]
            if wiz.group_by_location:
                groupby.append("location_id")
                read_fields.append("location_id")

            quant_groups = wiz.env["stock.quant"].sudo().read_group(
                domain,
                read_fields,
                groupby,
                lazy=False,
            )

            # Si agrupas por ubicación, vamos a reagrupar por bucket (para que cuadre con fechas)
            # Si NO agrupas por ubicación, el bucket será "scope" del wizard (pueden ser varias)
            aggregated = {}

            if wiz.group_by_location:
                # (product, bucket) -> qty_sum
                for g in quant_groups:
                    product_id = g.get("product_id") and g["product_id"][0]
                    loc_id = g.get("location_id") and g["location_id"][0]
                    if not product_id or not loc_id:
                        continue
                    bucket_id = loc_to_bucket.get(loc_id)
                    if not bucket_id:
                        continue
                    key = (product_id, bucket_id)
                    aggregated[key] = aggregated.get(key, 0.0) + (g.get("quantity", 0.0) or 0.0)
            else:
                # No agrupado por ubicación: un solo “bucket” lógico para la fila.
                # Si hay múltiples buckets (varias location_ids), usamos bucket_id = 0 y etiqueta lista.
                for g in quant_groups:
                    product_id = g.get("product_id") and g["product_id"][0]
                    if not product_id:
                        continue
                    key = (product_id, 0)
                    aggregated[key] = aggregated.get(key, 0.0) + (g.get("quantity", 0.0) or 0.0)

            # Etiqueta de ubicación cuando NO agrupas por ubicación
            if wiz.location_ids:
                locations_label = ", ".join(wiz.location_ids.mapped("display_name"))
            elif wiz.warehouse_id and wiz.warehouse_id.lot_stock_id:
                locations_label = wiz.warehouse_id.lot_stock_id.display_name
            else:
                locations_label = "-"

            # Para nombre de bucket cuando agrupas
            bucket_name_by_id = {b.id: b.display_name for b in bucket_locations}

            def _write_dt(r, c, dt_val):
                if not dt_val:
                    sheet.write(r, c, "", text_fmt)
                    return
                dt_val = self._dt_to_datetime(wiz, dt_val)
                if not dt_val:
                    sheet.write(r, c, "", text_fmt)
                    return
                dt_local = fields.Datetime.context_timestamp(wiz, dt_val)
                sheet.write_datetime(r, c, dt_local.replace(tzinfo=None), dt_fmt)

            # Escribir filas
            row += 1
            Product = wiz.env["product.product"].sudo()

            # Orden estable por nombre
            sorted_keys = sorted(
                aggregated.keys(),
                key=lambda k: (Product.browse(k[0]).display_name or "", k[1] or 0)
            )

            for (product_id, bucket_id), qty in [(k, aggregated[k]) for k in sorted_keys]:
                product = Product.browse(product_id)

                name = product.display_name or ""
                sku = product.default_code or ""
                categ = product.categ_id.complete_name or ""

                if wiz.group_by_location:
                    loc_name = bucket_name_by_id.get(bucket_id, "-")
                    first_in = first_in_map.get((product_id, bucket_id))
                    last_out = last_out_map.get((product_id, bucket_id))
                else:
                    # Consolidado: primer ingreso = mínimo entre buckets; última salida = máximo entre buckets
                    loc_name = locations_label

                    # Si hay buckets definidos, agregamos de todos los buckets:
                    if bucket_locations:
                        all_in = []
                        all_out = []
                        for bid in bucket_locations.ids:
                            dt_in = first_in_map.get((product_id, bid))
                            if dt_in:
                                all_in.append(dt_in)
                            dt_out = last_out_map.get((product_id, bid))
                            if dt_out:
                                all_out.append(dt_out)
                        first_in = min(all_in) if all_in else False
                        last_out = max(all_out) if all_out else False
                    else:
                        first_in = False
                        last_out = False

                cost = product.standard_price or 0.0
                sale = product.list_price or 0.0
                valued_company = qty * cost

                col = 0
                sheet.write(row, col, name, text_fmt);
                col += 1
                sheet.write(row, col, sku, text_fmt);
                col += 1
                sheet.write(row, col, categ, text_fmt);
                col += 1
                sheet.write(row, col, loc_name or "-", text_fmt);
                col += 1
                sheet.write_number(row, col, qty, qty_fmt);
                col += 1

                _write_dt(row, col, first_in);
                col += 1
                _write_dt(row, col, last_out);
                col += 1

                sheet.write_number(row, col, cost, num_fmt);
                col += 1
                sheet.write_number(row, col, sale, num_fmt);
                col += 1
                sheet.write_number(row, col, valued_company, num_fmt);
                col += 1

                for ccy in currencies:
                    if ccy == company_currency:
                        continue
                    valued_other = company_currency._convert(valued_company, ccy, company, today)
                    sheet.write_number(row, col, valued_other, num_fmt)
                    col += 1

                row += 1

            # Anchos
            col_widths = [
                             28, 12, 24, 28, 14, 18, 18, 14, 16, 18
                         ] + [18 for _ in extra_headers]
            for i, w in enumerate(col_widths):
                sheet.set_column(i, i, w)
