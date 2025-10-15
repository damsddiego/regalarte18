# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.tools import date_utils
from datetime import datetime, date, time
import calendar

class ConsignCxcXlsx(models.AbstractModel):
    _name = "report.sale_stock_sng.consign_cxc_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "XLSX - Reporte Consignaciones y CxC"



    # =========================
    #       HELPERS
    # =========================
    def _month_range(self, date_from, date_to):
        """Genera (y_from, m_from) ... (y_to, m_to) inclusive."""
        cur = date(date_from.year, date_from.month, 1)
        end = date(date_to.year, date_to.month, 1)
        while cur <= end:
            yield cur.year, cur.month
            # avanzar 1 mes
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

    def _month_bounds(self, y, m):
        """Devuelve (start_date, end_date) del mes y-m."""
        start = date(y, m, 1)
        last_day = calendar.monthrange(y, m)[1]
        end = date(y, m, last_day)
        return start, end

    def _partner_root_location(self, partner):
        """Ubicación raíz del cliente para valorización:
           - preferimos partner.sale_location_id si es 'internal'
           - si no, property_stock_customer si es 'internal'
           - si ninguna, None
        """
        loc = getattr(partner, "sale_location_id", False)
        if loc and getattr(loc, "usage", "") == "internal":
            return loc
        loc = getattr(partner, "property_stock_customer", False)
        if loc and getattr(loc, "usage", "") == "internal":
            return loc
        return None

    def _intersects_locations(self, root_loc, allowed_locs):
        """True si root_loc está dentro del conjunto de allowed_locs (child_of)."""
        if not root_loc:
            return False
        if not allowed_locs:
            return True
        # ¿root_loc es hija de alguna allowed?
        return bool(self.env["stock.location"].search_count([
            ("id", "=", root_loc.id),
            ("id", "child_of", allowed_locs.ids),
        ]))

    def _valued_stock_now(self, partner, restrict_locs=None):
        """Valorizado actual (ahora) en la bodega del cliente.
           Suma quants de (root_loc child_of) * standard_price.
           Si restrict_locs (wizard.location_ids) está presente, solo considera
           si la raíz del partner cae bajo esas ubicaciones.
        """
        root = self._partner_root_location(partner)
        if not root:
            return 0.0

        if restrict_locs and not self._intersects_locations(root, restrict_locs):
            return 0.0

        Quant = self.env["stock.quant"].sudo()
        quants = Quant.search([
            ("location_id", "child_of", root.id),
            # En consignación podrías querer owner_id = False o = partner.id;
            # Si necesitas forzar owner, agrega condición aquí.
        ])
        total = 0.0
        for q in quants:
            # Costo de referencia: standard_price (puedes cambiar a valor de valoración si usas AVCO/FIFO con valor)
            cost = q.product_id.standard_price or 0.0
            qty = q.quantity or 0.0
            total += qty * cost
        return total

    def _receivable_in_month(self, partner, m_start, m_end):
        """Saldo por cobrar (residual) de facturas del mes (por invoice_date en el rango).
           Sumamos amount_residual_signed de las facturas de ese mes que estén posteadas.
           Si prefieres por vencimiento (invoice_date_due) cámbialo abajo.
        """
        invs = self.env["account.move"].search_read(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("partner_id", "=", partner.id),
                ("invoice_date", ">=", m_start),
                ("invoice_date", "<=", m_end),
            ],
            ["amount_residual_signed"],
        )
        return sum(inv.get("amount_residual_signed", 0.0) for inv in invs)

    def _sales_total_in_month(self, partner, m_start, m_end):
        """Total de ventas del mes (por invoice_date)."""
        invs = self.env["account.move"].search_read(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("partner_id", "=", partner.id),
                ("invoice_date", ">=", m_start),
                ("invoice_date", "<=", m_end),
            ],
            ["amount_total_signed"],
        )
        return sum(inv.get("amount_total_signed", 0.0) for inv in invs)

    def _last_out_picking_date(self, partner, upper_dt):
        picking = self.env["stock.picking"].search(
            [
                ("picking_type_code", "=", "outgoing"),
                ("partner_id", "=", partner.id),
                ("state", "=", "done"),
                ("date_done", "<=", upper_dt),
            ],
            order="date_done desc",
            limit=1,
        )
        return picking.date_done

    def _last_invoice_date(self, partner, upper_d):
        inv = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("partner_id", "=", partner.id),
                ("invoice_date", "<=", upper_d),
            ],
            order="invoice_date desc, id desc",
            limit=1,
        )
        return inv.invoice_date

    # =========================
    #     REPORTE XLSX
    # =========================
    def generate_xlsx_report(self, workbook, data, wizards):
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})
        wrap = workbook.add_format({"text_wrap": True})
        h2 = workbook.add_format({"bold": True, "bg_color": "#DDDDDD"})

        for wiz in wizards:
            ws = workbook.add_worksheet(_("Consignaciones y CxC"))
            row = 0

            # Fechas efectivas
            date_from = wiz._get_date_from_effective()
            date_to = wiz.date_to
            date_to_dt = date_utils.end_of(date_to, "day")

            # Encabezado
            ws.write(row, 0, _("Reporte de consignaciones y CxC"), bold);
            row += 2
            ws.write(row, 0, _("Fecha desde"));
            ws.write_datetime(row, 1, datetime.combine(date_from, time.min), date_fmt);
            row += 1
            ws.write(row, 0, _("Fecha hasta"));
            ws.write_datetime(row, 1, datetime.combine(date_to, time.min), date_fmt);
            row += 1

            # Bodegas (texto)
            locs_txt = ", ".join(wiz.location_ids.mapped("complete_name")) if wiz.location_ids else _(
                "Todas las internas")
            ws.write(row, 0, _("Bodegas"));
            ws.write(row, 1, locs_txt);
            row += 1

            # Vendedor
            ws.write(row, 0, _("Vendedor"));
            ws.write(row, 1, wiz.user_id.name or _("Todos"));
            row += 2

            # Encabezados de tabla
            headers = [
                _("Cod cliente"), _("Descripción"), _("Vendedor"), _("RUTA/ZONA"),
                _("Ultimo traslado Bodega cliente"), _("Ultima factura realizada"),
                _("Colones [1]"), _("CXC (mes)"), _("GENERAL (mes)"),
                _("Valorizado actual"),
            ]
            for col, h in enumerate(headers):
                ws.write(row, col, h, bold)
            header_row = row
            row += 1

            # Partners base
            partner_domain = [("customer_rank", ">", 0), ("active", "=", True)]
            if wiz.user_id:
                partner_domain.append(("user_id", "=", wiz.user_id.id))
            if wiz.location_ids:
                # Considera clientes cuya sale_location_id/property_stock_customer intersecte con las seleccionadas
                partner_domain += ["|", ("sale_location_id", "in", wiz.location_ids.ids),
                                   ("property_stock_customer", "in", wiz.location_ids.ids)]
            partners = self.env["res.partner"].search(partner_domain)

            # Totales generales
            grand_currency = grand_cxc = grand_general = grand_valued = 0.0

            # Iterar por meses
            for y, m in self._month_range(date_from, date_to):
                m_start, m_end = self._month_bounds(y, m)

                # Subtotales del mes
                sub_currency = sub_cxc = sub_general = sub_valued = 0.0

                # Título del mes
                ws.write(row, 0, "%s %s" % (_(calendar.month_name[m]), y), h2)
                row += 1

                for p in partners:
                    # Cálculos por mes
                    cxc_m = self._receivable_in_month(p, m_start, m_end)
                    gen_m = self._sales_total_in_month(p, m_start, m_end)

                    # Si no hay nada en el mes, no lo listamos
                    if not cxc_m and not gen_m:
                        continue

                    # Valorizado actual (ahora) en su bodega específica (restringido por locs del wizard)
                    valued_now = self._valued_stock_now(p, wiz.location_ids)

                    # Columna "Colones [1]" (tu regla actual): general - cxc; si 0, usar general
                    currency = float(gen_m - cxc_m)
                    if currency == 0:
                        currency = gen_m

                    # Datos descriptivos
                    code = getattr(p, "client_code", None) or p.vat or str(p.id)
                    desc = p.name or ""
                    vendedor = p.user_id.name or ""
                    ruta = ", ".join(filter(None, [
                        p.street, p.city,
                        p.state_id and p.state_id.name,
                        p.country_id and p.country_id.name
                    ])) or (p.contact_address or "")

                    last_pick_dt = self._last_out_picking_date(p, date_to_dt)
                    last_inv_dt = self._last_invoice_date(p, m_end)

                    # Escribir fila
                    col = 0
                    ws.write(row, col, code);
                    col += 1
                    ws.write(row, col, desc);
                    col += 1
                    ws.write(row, col, vendedor);
                    col += 1
                    ws.write(row, col, ruta, wrap);
                    col += 1
                    if last_pick_dt:
                        ws.write_datetime(row, col, last_pick_dt, date_fmt)
                    else:
                        ws.write(row, col, "")
                    col += 1
                    if last_inv_dt:
                        ws.write_datetime(row, col, datetime.combine(last_inv_dt, time.min), date_fmt)
                    else:
                        ws.write(row, col, "")
                    col += 1
                    ws.write_number(row, col, currency or 0.0, money);
                    col += 1
                    ws.write_number(row, col, cxc_m or 0.0, money);
                    col += 1
                    ws.write_number(row, col, gen_m or 0.0, money);
                    col += 1
                    ws.write_number(row, col, valued_now or 0.0, money);
                    col += 1
                    row += 1

                    # Subtotales
                    sub_currency += currency or 0.0
                    sub_cxc += cxc_m or 0.0
                    sub_general += gen_m or 0.0
                    sub_valued += valued_now or 0.0

                # Fila de subtotal del mes
                ws.write(row, 0, _("SUBTOTAL %s %s") % (_(calendar.month_name[m]), y), bold)
                ws.write(row, 1, "");
                ws.write(row, 2, "");
                ws.write(row, 3, "")
                ws.write(row, 4, "");
                ws.write(row, 5, "")
                ws.write_number(row, 6, sub_currency, money)
                ws.write_number(row, 7, sub_cxc, money)
                ws.write_number(row, 8, sub_general, money)
                ws.write_number(row, 9, sub_valued, money)
                row += 2

                # Acumular totales generales
                grand_currency += sub_currency
                grand_cxc += sub_cxc
                grand_general += sub_general
                grand_valued += sub_valued

            # Totales generales
            ws.write(row, 0, _("TOTALES GENERALES"), bold)
            ws.write(row, 1, "");
            ws.write(row, 2, "");
            ws.write(row, 3, "")
            ws.write(row, 4, "");
            ws.write(row, 5, "")
            ws.write_number(row, 6, grand_currency, money)
            ws.write_number(row, 7, grand_cxc, money)
            ws.write_number(row, 8, grand_general, money)
            ws.write_number(row, 9, grand_valued, money)
            row += 1

            # Presentación
            widths = [14, 30, 22, 35, 24, 22, 14, 18, 18, 18]
            for i, w in enumerate(widths):
                ws.set_column(i, i, w)
            ws.freeze_panes(header_row + 1, 0)
            ws.autofilter(header_row, 0, row - 1, len(headers) - 1)

    # def generate_xlsx_report(self, workbook, data, wizards):
    #     date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
    #     bold = workbook.add_format({"bold": True})
    #     money = workbook.add_format({"num_format": "#,##0.00"})
    #     wrap = workbook.add_format({"text_wrap": True})
    #
    #     for wiz in wizards:
    #         ws = workbook.add_worksheet(_("Consignaciones y CxC"))
    #         row = 0
    #
    #         # Fechas efectivas
    #         date_from = wiz._get_date_from_effective()
    #         date_to = wiz.date_to
    #         date_to_dt = date_utils.end_of(date_to, "day")
    #
    #         # Encabezado
    #         ws.write(row, 0, _("Reporte de consignaciones y CxC"), bold);
    #         row += 2
    #         ws.write(row, 0, _("Fecha desde"));
    #         ws.write_datetime(row, 1, datetime.combine(date_from, time.min), date_fmt);
    #         row += 1
    #         ws.write(row, 0, _("Fecha hasta"));
    #         ws.write_datetime(row, 1, datetime.combine(date_to, time.min), date_fmt);
    #         row += 1
    #
    #         # Bodegas (texto)
    #         locs_txt = ", ".join(wiz.location_ids.mapped("complete_name")) if wiz.location_ids else _(
    #             "Todas las internas")
    #         ws.write(row, 0, _("Bodegas"));
    #         ws.write(row, 1, locs_txt);
    #         row += 1
    #
    #         # Vendedor
    #         ws.write(row, 0, _("Vendedor"));
    #         ws.write(row, 1, wiz.user_id.name or _("Todos"));
    #         row += 2
    #
    #         # Encabezados de tabla
    #         headers = [
    #             _("Cod cliente"), _("Descripción"), _("Vendedor"), _("RUTA/ZONA"),
    #             _("Ultimo traslado Bodega cliente"), _("Ultima factura realizada"),
    #             _("Colones [1]"), _("CXC"), _("GENERAL"),
    #         ]
    #         for col, h in enumerate(headers):
    #             ws.write(row, col, h, bold)
    #         header_row = row
    #         row += 1
    #
    #         # Dominio partners
    #         partner_domain = [("customer_rank", ">", 0), ("active", "=", True)]
    #         if wiz.user_id:
    #             partner_domain.append(("user_id", "=", wiz.user_id.id))
    #         if wiz.location_ids:
    #             partner_domain += ["|",
    #                                ("sale_location_id", "in", wiz.location_ids.ids),
    #                                ("property_stock_customer", "in", wiz.location_ids.ids),
    #                                ]
    #         partners = self.env["res.partner"].search(partner_domain)
    #
    #         # Helpers
    #         def _partner_currency(p):
    #             pricelist = p.property_product_pricelist
    #             return pricelist.currency_id if pricelist else p.company_id.currency_id
    #
    #         def _last_out_picking_date(p):
    #             picking = self.env["stock.picking"].search(
    #                 [
    #                     ("picking_type_code", "=", "outgoing"),
    #                     ("partner_id", "=", p.id),
    #                     ("state", "=", "done"),
    #                     ("date_done", "<=", date_to_dt),
    #                 ],
    #                 order="date_done desc",
    #                 limit=1,
    #             )
    #             return picking.date_done  # datetime o False
    #
    #         def _receivable_balance(p):
    #             aml = self.env["account.move.line"].search_read(
    #                 [
    #                     ("partner_id", "=", p.id),
    #                     ("account_id.account_type", "=", "asset_receivable"),
    #                     ("parent_state", "=", "posted"),
    #                     ("reconciled", "=", False),
    #                 ],
    #                 ["amount_residual"],
    #             )
    #             return sum(line.get("amount_residual", 0.0) for line in aml)
    #
    #         def _total_sales_in_range(p):
    #             invs = self.env["account.move"].search_read(
    #                 [
    #                     ("move_type", "=", "out_invoice"),
    #                     ("state", "=", "posted"),
    #                     ("partner_id", "=", p.id),
    #                     ("invoice_date", ">=", date_from),
    #                     ("invoice_date", "<=", date_to),
    #                 ],
    #                 ["amount_total_signed"],
    #             )
    #             return sum(inv["amount_total_signed"] for inv in invs)
    #
    #         def _last_invoice_date(p):
    #             inv = self.env["account.move"].search(
    #                 [
    #                     ("move_type", "=", "out_invoice"),
    #                     ("state", "=", "posted"),
    #                     ("partner_id", "=", p.id),
    #                     ("invoice_date", "<=", date_to),
    #                 ],
    #                 order="invoice_date desc, id desc",
    #                 limit=1,
    #             )
    #             return inv.invoice_date  # date o False
    #
    #         # Acumuladores
    #         total_currency = 0.0
    #         total_cxc = 0.0
    #         total_general = 0.0
    #
    #         for p in partners:
    #             # Calcular una sola vez por partner
    #             cxc = _receivable_balance(p)
    #             general = _total_sales_in_range(p)
    #
    #             # Filtrado: solo mostrar con CxC != 0 o General != 0
    #             if not cxc and not general:
    #                 continue
    #
    #             code = getattr(p, "client_code", None) or p.vat or str(p.id)
    #             desc = p.name or ""
    #             vendedor = p.user_id.name or ""
    #             ruta = ", ".join(filter(None, [
    #                 p.street, p.city,
    #                 p.state_id and p.state_id.name,
    #                 p.country_id and p.country_id.name
    #             ])) or (p.contact_address or "")
    #
    #             last_pick_dt = _last_out_picking_date(p)  # datetime
    #             last_inv_dt = _last_invoice_date(p)  # date
    #
    #             # "Colones [1]": tu lógica previa
    #             currency = float(general - cxc)
    #             if currency == 0:
    #                 currency = general
    #
    #             # Acumular
    #             total_currency += float(currency or 0.0)
    #             total_cxc += float(cxc or 0.0)
    #             total_general += float(general or 0.0)
    #
    #             # Escribir fila
    #             col = 0
    #             ws.write(row, col, code);
    #             col += 1
    #             ws.write(row, col, desc);
    #             col += 1
    #             ws.write(row, col, vendedor);
    #             col += 1
    #             ws.write(row, col, ruta, wrap);
    #             col += 1
    #             if last_pick_dt:
    #                 ws.write_datetime(row, col, last_pick_dt, date_fmt)
    #             else:
    #                 ws.write(row, col, "")
    #             col += 1
    #             if last_inv_dt:
    #                 ws.write_datetime(row, col, datetime.combine(last_inv_dt, time.min), date_fmt)
    #             else:
    #                 ws.write(row, col, "")
    #             col += 1
    #             ws.write_number(row, col, currency or 0.0, money);
    #             col += 1
    #             ws.write_number(row, col, cxc or 0.0, money);
    #             col += 1
    #             ws.write_number(row, col, general or 0.0, money);
    #             col += 1
    #             row += 1
    #
    #         # Línea en blanco y totales
    #         row += 1
    #         ws.write(row, 0, _("TOTALES"), bold)
    #         ws.write(row, 1, "");
    #         ws.write(row, 2, "");
    #         ws.write(row, 3, "")
    #         ws.write(row, 4, "");
    #         ws.write(row, 5, "")
    #
    #         ws.write_number(row, 6, total_currency, money)
    #         ws.write_number(row, 7, total_cxc, money)
    #         ws.write_number(row, 8, total_general, money)
    #
    #         # Presentación
    #         widths = [14, 30, 22, 35, 24, 22, 14, 18, 18]
    #         for i, w in enumerate(widths):
    #             ws.set_column(i, i, w)
    #         # Congelar encabezados (opcional)
    #         ws.freeze_panes(header_row + 1, 0)
    #         # Autofiltro (opcional)
    #         ws.autofilter(header_row, 0, row - 2, len(headers) - 1)

    # def generate_xlsx_report(self, workbook, data, wizards):
    #     date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
    #     bold = workbook.add_format({"bold": True})
    #     money = workbook.add_format({"num_format": "#,##0.00"})
    #     wrap = workbook.add_format({"text_wrap": True})
    #
    #     for wiz in wizards:
    #         ws = workbook.add_worksheet(_("Consignaciones y CxC"))
    #         row = 0
    #
    #         # Fechas efectivas
    #         date_from = wiz._get_date_from_effective()
    #         date_to = wiz.date_to
    #         date_to_dt = date_utils.end_of(date_to, 'day')
    #
    #         # Encabezado
    #         ws.write(row, 0, _("Reporte de consignaciones y CxC"), bold); row += 2
    #         ws.write(row, 0, _("Fecha desde")); ws.write_datetime(row, 1, datetime.combine(date_from, time.min), date_fmt); row += 1
    #         ws.write(row, 0, _("Fecha hasta")); ws.write_datetime(row, 1, datetime.combine(date_to, time.min), date_fmt); row += 1
    #
    #         # Bodegas (texto)
    #         locs_txt = ", ".join(wiz.location_ids.mapped("complete_name")) if wiz.location_ids else _("Todas las internas")
    #         ws.write(row, 0, _("Bodegas")); ws.write(row, 1, locs_txt); row += 1
    #
    #         # Vendedor
    #         ws.write(row, 0, _("Vendedor")); ws.write(row, 1, wiz.user_id.name or _("Todos")); row += 2
    #
    #         # Encabezados de tabla
    #         headers = [
    #             _("Cod cliente"), _("Descripción"), _("Vendedor"), _("RUTA/ZONA"),
    #             _("Ultimo traslado Bodega cliente"), _("Ultima factura realizada"),
    #             _("Colones [1]"), _("CXC"), _("GENERAL"),
    #         ]
    #         for col, h in enumerate(headers):
    #             ws.write(row, col, h, bold)
    #         row += 1
    #
    #         # Dominio partners
    #         partner_domain = [("customer_rank", ">", 0), ("active", "=", True)]
    #         if wiz.user_id:
    #             partner_domain.append(("user_id", "=", wiz.user_id.id))
    #         if wiz.location_ids:
    #             partner_domain += ["|",
    #                 ("sale_location_id", "in", wiz.location_ids.ids),
    #                 ("property_stock_customer", "in", wiz.location_ids.ids),
    #             ]
    #         partners = self.env["res.partner"].search(partner_domain)
    #
    #         # Helpers
    #         def _partner_currency(p):
    #             pricelist = p.property_product_pricelist
    #             return pricelist.currency_id if pricelist else p.company_id.currency_id
    #
    #         def _last_out_picking_date(p):
    #             picking = self.env["stock.picking"].search(
    #                 [
    #                     ("picking_type_code", "=", "outgoing"),
    #                     ("partner_id", "=", p.id),
    #                     ("state", "=", "done"),
    #                     ("date_done", "<=", date_to_dt),
    #                 ],
    #                 order="date_done desc",
    #                 limit=1,
    #             )
    #             return picking.date_done  # datetime o False
    #
    #         def _last_invoice_date(p):
    #             inv = self.env["account.move"].search(
    #                 [
    #                     ("move_type", "=", "out_invoice"),
    #                     ("state", "=", "posted"),
    #                     ("partner_id", "=", p.id),
    #                     ("invoice_date", "<=", date_to),
    #                 ],
    #                 order="invoice_date desc, id desc",
    #                 limit=1,
    #             )
    #             return inv.invoice_date  # date o False
    #
    #         def _receivable_balance(p):
    #             aml = self.env["account.move.line"].search_read(
    #                 [
    #                     ("partner_id", "=", p.id),
    #                     ("account_id.account_type", "=", "asset_receivable"),
    #                     ("parent_state", "=", "posted"),
    #                     ("reconciled", "=", False),
    #                 ],
    #                 ["amount_residual"],
    #             )
    #             return sum(line.get("amount_residual", 0.0) for line in aml)
    #
    #         def _total_sales_in_range(p):
    #             invs = self.env["account.move"].search_read(
    #                 [
    #                     ("move_type", "=", "out_invoice"),
    #                     ("state", "=", "posted"),
    #                     ("partner_id", "=", p.id),
    #                     ("invoice_date", ">=", date_from),
    #                     ("invoice_date", "<=", date_to),
    #                 ],
    #                 ["amount_total_signed"],
    #             )
    #             return sum(inv["amount_total_signed"] for inv in invs)
    #
    #         total_currency = 0.0
    #         total_cxc = 0.0
    #         total_general = 0.0
    #         for p in partners:
    #             if _receivable_balance(p) != 0 or _total_sales_in_range(p) != 0:
    #                 code = p.client_code or p.vat or str(p.id)
    #                 desc = p.name or ""
    #                 vendedor = p.user_id.name or ""
    #                 ruta = ", ".join(filter(None, [
    #                     p.street, p.city,
    #                     p.state_id and p.state_id.name,
    #                     p.country_id and p.country_id.name
    #                 ])) or (p.contact_address or "")
    #
    #                 last_pick_dt = _last_out_picking_date(p)
    #                 last_inv_dt = _last_invoice_date(p)
    #                 currency = float(_total_sales_in_range(p) - _receivable_balance(p))
    #                 if currency == 0:
    #                     currency = _total_sales_in_range(p)
    #                 cxc = _receivable_balance(p)
    #                 general = _total_sales_in_range(p)
    #
    #                 total_currency += float(currency or 0.0)
    #                 total_cxc += float(cxc or 0.0)
    #                 total_general += float(general or 0.0)
    #
    #                 col = 0
    #                 ws.write(row, col, code); col += 1
    #                 ws.write(row, col, desc); col += 1
    #                 ws.write(row, col, vendedor); col += 1
    #                 ws.write(row, col, ruta, wrap); col += 1
    #                 ws.write_datetime(row, col, last_pick_dt, date_fmt) if last_pick_dt else ws.write(row, col, ""); col += 1
    #                 ws.write_datetime(row, col, datetime.combine(last_inv_dt, time.min), date_fmt) if last_inv_dt else ws.write(row, col, ""); col += 1
    #                 ws.write_number(row, col, currency or 0, money); col += 1
    #                 ws.write_number(row, col, cxc or 0.0, money); col += 1
    #                 ws.write_number(row, col, general or 0.0, money); col += 1
    #                 row += 1
    #         ws.write(row, 0, _("TOTALES"), bold)
    #
    #         ws.write(row, 1, "")
    #         ws.write(row, 2, "")
    #         ws.write(row, 3, "")
    #         ws.write(row, 4, "")
    #         ws.write(row, 5, "")
    #
    #         ws.write_number(row, 6, total_currency, money)
    #         ws.write_number(row, 7, total_cxc, money)  # Total CxC
    #         ws.write_number(row, 8, total_general, money)
    #         widths = [14, 30, 22, 35, 24, 22, 14, 18, 18]
    #         for i, w in enumerate(widths):
    #             ws.set_column(i, i, w)
