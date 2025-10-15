# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.tools import date_utils
from datetime import datetime, date, time as dt_time
import calendar

class ConsignCxcXlsx(models.AbstractModel):
    _name = "report.sale_stock_sng.consign_cxc_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "XLSX - Reporte Consignaciones y CxC"

    # =========================
    #       HELPERS (fechas)
    # =========================
    def _month_range(self, date_from: date, date_to: date):
        cur = date(date_from.year, date_from.month, 1)
        end = date(date_to.year, date_to.month, 1)
        while cur <= end:
            yield cur.year, cur.month
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)

    def _month_bounds(self, y: int, m: int):
        start = date(y, m, 1)
        last_day = calendar.monthrange(y, m)[1]
        end = date(y, m, last_day)
        return start, end

    def _month_label(self, y: int, m: int):
        dt = date(y, m, 1)
        lang = (self.env.user.lang or 'es_ES').replace('_', '-')
        try:
            from babel.dates import format_date as babel_format_date
            name = babel_format_date(dt, format='LLLL yyyy', locale=lang)
            return name[:1].upper() + name[1:]
        except Exception:
            meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                     'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
            return f"{meses[m-1]} {y}"

    # =========================
    #       HELPERS (stock)
    # =========================
    def _partner_root_location(self, partner):
        """Raíz de bodega del cliente.
        1) partner.sale_location_id si existe
        2) si no, property_stock_customer
        (No filtramos por 'usage' para no excluir consignaciones)."""
        loc = getattr(partner, "sale_location_id", False)
        if loc:
            return loc
        loc = getattr(partner, "property_stock_customer", False)
        if loc:
            return loc
        return None

    def _intersects_locations(self, root_loc, allowed_locs):
        if not root_loc:
            return False
        if not allowed_locs:
            return True
        return bool(self.env["stock.location"].search_count([
            ("id", "=", root_loc.id),
            ("id", "child_of", allowed_locs.ids),
        ]))

    def _valued_stock_now(self, partner, restrict_locs=None):
        """Valor actual de TODO el stock en la bodega del cliente (root child_of).
        1) Si existe 'quant.value', se usa (valor contable).
        2) Si no, qty × standard_price (con fallback al template).
        3) Aplica intersección real con wiz.location_ids (AND)."""
        root = self._partner_root_location(partner)
        if not root:
            return 0.0

        domain = [('location_id', '=', root.id)]

        Quant = self.env["stock.quant"].sudo().with_context(active_test=False).search(domain)
        total = 0
        for a in Quant:
            total += a.quantity * a.product_id.standard_price
        return total

    # =========================
    #     HELPERS (finanzas)
    # =========================
    def _receivable_in_month(self, partner, m_start: date, m_end: date):
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

    def _sales_total_in_month(self, partner, m_start: date, m_end: date):
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

    def _last_out_picking_date(self, partner, upper_dt: datetime):
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

    def _last_invoice_date(self, partner, upper_d: date):
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

    def _last_invoice_in_month(self, partner, m_start: date, m_end: date):
        return self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("partner_id", "=", partner.id),
                ("invoice_date", ">=", m_start),
                ("invoice_date", "<=", m_end),
            ],
            order="invoice_date desc, id desc",
            limit=1,
        )

    # =========================
    #        XLSX
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
            ws.write(row, 0, _("Reporte de consignaciones y CxC"), bold); row += 2
            ws.write(row, 0, _("Fecha desde"))
            ws.write_datetime(row, 1, datetime.combine(date_from, dt_time.min), date_fmt); row += 1
            ws.write(row, 0, _("Fecha hasta"))
            ws.write_datetime(row, 1, datetime.combine(date_to, dt_time.min), date_fmt); row += 1

            # Bodegas (texto)
            locs_txt = ", ".join(wiz.location_ids.mapped("complete_name")) if wiz.location_ids else _("Todas las internas")
            ws.write(row, 0, _("Bodegas")); ws.write(row, 1, locs_txt); row += 1

            # Vendedor
            ws.write(row, 0, _("Vendedor")); ws.write(row, 1, wiz.user_id.name or _("Todos")); row += 2

            # Encabezados de tabla
            headers = [
                _("Cod cliente"), _("Descripción"), _("Vendedor"), _("Equipo de ventas"),
                _("Último traslado Bodega cliente"), _("Última factura realizada"), _("Asiento"),
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
                partner_domain += ["|",
                    ("sale_location_id", "in", wiz.location_ids.ids),
                    ("property_stock_customer", "in", wiz.location_ids.ids),
                ]
            partners = self.env["res.partner"].search(partner_domain)

            # Totales generales
            grand_currency = grand_cxc = grand_general = grand_valued = 0.0

            # Iterar por meses
            for y, m in self._month_range(date_from, date_to):
                m_start, m_end = self._month_bounds(y, m)

                # Subtotales del mes
                sub_currency = sub_cxc = sub_general = sub_valued = 0.0

                # Título del mes
                ws.write(row, 0, self._month_label(y, m), h2)
                row += 1

                for p in partners:
                    # Cálculos por mes
                    cxc_m = self._receivable_in_month(p, m_start, m_end)
                    gen_m = self._sales_total_in_month(p, m_start, m_end)
                    if not cxc_m and not gen_m:
                        continue

                    # Última factura del mes → team y asiento
                    inv_last = self._last_invoice_in_month(p, m_start, m_end)
                    team_name = inv_last.team_id.name if inv_last and inv_last.team_id else ""
                    asiento_name = inv_last.name if inv_last else ""

                    # Valorizado actual en bodega del cliente (respeta wizard.location_ids)
                    valued_now = self._valued_stock_now(p, wiz.location_ids)

                    # "Colones [1]"
                    currency = float(gen_m - cxc_m)
                    if currency == 0:
                        currency = gen_m

                    # Datos descriptivos
                    code = getattr(p, "client_code", None) or p.vat or str(p.id)
                    desc = p.name or ""
                    vendedor = p.user_id.name or ""

                    last_pick_dt = self._last_out_picking_date(p, date_to_dt)
                    last_inv_dt = self._last_invoice_date(p, m_end)

                    # Fila
                    col = 0
                    ws.write(row, col, code); col += 1
                    ws.write(row, col, desc); col += 1
                    ws.write(row, col, vendedor); col += 1
                    ws.write(row, col, team_name, wrap); col += 1

                    if last_pick_dt:
                        ws.write_datetime(row, col, last_pick_dt, date_fmt)
                    else:
                        ws.write(row, col, "")
                    col += 1

                    if last_inv_dt:
                        ws.write_datetime(row, col, datetime.combine(last_inv_dt, dt_time.min), date_fmt)
                    else:
                        ws.write(row, col, "")
                    col += 1

                    ws.write(row, col, asiento_name or ""); col += 1
                    ws.write_number(row, col, currency or 0.0, money); col += 1
                    ws.write_number(row, col, cxc_m or 0.0, money); col += 1
                    ws.write_number(row, col, gen_m or 0.0, money); col += 1
                    ws.write_number(row, col, valued_now or 0.0, money); col += 1
                    row += 1

                    # Subtotales del mes
                    sub_currency += currency or 0.0
                    sub_cxc += cxc_m or 0.0
                    sub_general += gen_m or 0.0
                    sub_valued += valued_now or 0.0

                # Subtotal del mes
                ws.write(row, 0, _("SUBTOTAL ") + self._month_label(y, m), bold)
                ws.write(row, 1, ""); ws.write(row, 2, ""); ws.write(row, 3, "")
                ws.write(row, 4, ""); ws.write(row, 5, ""); ws.write(row, 6, "")
                ws.write_number(row, 7, sub_currency, money)
                ws.write_number(row, 8, sub_cxc, money)
                ws.write_number(row, 9, sub_general, money)
                ws.write_number(row, 10, sub_valued, money)
                row += 2

                # Totales generales
                grand_currency += sub_currency
                grand_cxc += sub_cxc
                grand_general += sub_general
                grand_valued += sub_valued

            # Totales generales
            ws.write(row, 0, _("TOTALES GENERALES"), bold)
            ws.write(row, 1, ""); ws.write(row, 2, ""); ws.write(row, 3, "")
            ws.write(row, 4, ""); ws.write(row, 5, ""); ws.write(row, 6, "")
            ws.write_number(row, 7, grand_currency, money)
            ws.write_number(row, 8, grand_cxc, money)
            ws.write_number(row, 9, grand_general, money)
            ws.write_number(row, 10, grand_valued, money)
            row += 1

            # Presentación
            widths = [14, 30, 22, 26, 24, 22, 20, 14, 18, 18, 18]
            for i, w in enumerate(widths):
                ws.set_column(i, i, w)
            ws.freeze_panes(header_row + 1, 0)
            ws.autofilter(header_row, 0, row - 1, len(headers) - 1)
