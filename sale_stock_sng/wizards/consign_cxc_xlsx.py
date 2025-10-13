# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.tools import date_utils  # <-- importa date_utils
from datetime import datetime, date, time  # time para combinar fechas

class ConsignCxcXlsx(models.AbstractModel):
    _name = "report.sale_stock_sng.consign_cxc_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "XLSX - Reporte Consignaciones y CxC"

    def generate_xlsx_report(self, workbook, data, wizards):
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd"})
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})
        wrap = workbook.add_format({"text_wrap": True})

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
                _("Colones [1]"), _("CXC"), _("GENERAL"),
            ]
            for col, h in enumerate(headers):
                ws.write(row, col, h, bold)
            header_row = row
            row += 1

            # Dominio partners
            partner_domain = [("customer_rank", ">", 0), ("active", "=", True)]
            if wiz.user_id:
                partner_domain.append(("user_id", "=", wiz.user_id.id))
            if wiz.location_ids:
                partner_domain += ["|",
                                   ("sale_location_id", "in", wiz.location_ids.ids),
                                   ("property_stock_customer", "in", wiz.location_ids.ids),
                                   ]
            partners = self.env["res.partner"].search(partner_domain)

            # Helpers
            def _partner_currency(p):
                pricelist = p.property_product_pricelist
                return pricelist.currency_id if pricelist else p.company_id.currency_id

            def _last_out_picking_date(p):
                picking = self.env["stock.picking"].search(
                    [
                        ("picking_type_code", "=", "outgoing"),
                        ("partner_id", "=", p.id),
                        ("state", "=", "done"),
                        ("date_done", "<=", date_to_dt),
                    ],
                    order="date_done desc",
                    limit=1,
                )
                return picking.date_done  # datetime o False

            def _receivable_balance(p):
                aml = self.env["account.move.line"].search_read(
                    [
                        ("partner_id", "=", p.id),
                        ("account_id.account_type", "=", "asset_receivable"),
                        ("parent_state", "=", "posted"),
                        ("reconciled", "=", False),
                    ],
                    ["amount_residual"],
                )
                return sum(line.get("amount_residual", 0.0) for line in aml)

            def _total_sales_in_range(p):
                invs = self.env["account.move"].search_read(
                    [
                        ("move_type", "=", "out_invoice"),
                        ("state", "=", "posted"),
                        ("partner_id", "=", p.id),
                        ("invoice_date", ">=", date_from),
                        ("invoice_date", "<=", date_to),
                    ],
                    ["amount_total_signed"],
                )
                return sum(inv["amount_total_signed"] for inv in invs)

            def _last_invoice_date(p):
                inv = self.env["account.move"].search(
                    [
                        ("move_type", "=", "out_invoice"),
                        ("state", "=", "posted"),
                        ("partner_id", "=", p.id),
                        ("invoice_date", "<=", date_to),
                    ],
                    order="invoice_date desc, id desc",
                    limit=1,
                )
                return inv.invoice_date  # date o False

            # Acumuladores
            total_currency = 0.0
            total_cxc = 0.0
            total_general = 0.0

            for p in partners:
                # Calcular una sola vez por partner
                cxc = _receivable_balance(p)
                general = _total_sales_in_range(p)

                # Filtrado: solo mostrar con CxC != 0 o General != 0
                if not cxc and not general:
                    continue

                code = getattr(p, "client_code", None) or p.vat or str(p.id)
                desc = p.name or ""
                vendedor = p.user_id.name or ""
                ruta = ", ".join(filter(None, [
                    p.street, p.city,
                    p.state_id and p.state_id.name,
                    p.country_id and p.country_id.name
                ])) or (p.contact_address or "")

                last_pick_dt = _last_out_picking_date(p)  # datetime
                last_inv_dt = _last_invoice_date(p)  # date

                # "Colones [1]": tu lógica previa
                currency = float(general - cxc)
                if currency == 0:
                    currency = general

                # Acumular
                total_currency += float(currency or 0.0)
                total_cxc += float(cxc or 0.0)
                total_general += float(general or 0.0)

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
                ws.write_number(row, col, cxc or 0.0, money);
                col += 1
                ws.write_number(row, col, general or 0.0, money);
                col += 1
                row += 1

            # Línea en blanco y totales
            row += 1
            ws.write(row, 0, _("TOTALES"), bold)
            ws.write(row, 1, "");
            ws.write(row, 2, "");
            ws.write(row, 3, "")
            ws.write(row, 4, "");
            ws.write(row, 5, "")

            ws.write_number(row, 6, total_currency, money)
            ws.write_number(row, 7, total_cxc, money)
            ws.write_number(row, 8, total_general, money)

            # Presentación
            widths = [14, 30, 22, 35, 24, 22, 14, 18, 18]
            for i, w in enumerate(widths):
                ws.set_column(i, i, w)
            # Congelar encabezados (opcional)
            ws.freeze_panes(header_row + 1, 0)
            # Autofiltro (opcional)
            ws.autofilter(header_row, 0, row - 2, len(headers) - 1)

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
