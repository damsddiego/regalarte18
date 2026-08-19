# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class SngReporteConsLine(models.TransientModel):
    _name = "sng.reporte.cons.line"
    _description = "Línea Reporte Consignaciones"
    _order = "partner_id"

    wizard_id = fields.Many2one("sng.reporte.cons.wizard", ondelete="cascade")
    company_id = fields.Many2one("res.company", related="wizard_id.company_id", store=True, readonly=True)
    company_currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", readonly=True
    )
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    partner_code = fields.Char(string="Código", readonly=True)
    commercial_name = fields.Char(string="Nombre Comercial", readonly=True)
    sales_route_id = fields.Many2one(
        "sng.sales.route", string="Ruta", related="partner_id.sales_route_id", readonly=True
    )
    salesperson_id = fields.Many2one("res.partner", string="Vendedor", readonly=True)
    location_id = fields.Many2one("stock.location", string="Ubicación", readonly=True)
    last_entry_date = fields.Datetime(string="U Entrada", readonly=True)
    last_sale_date = fields.Datetime(string="U Venta", readonly=True)
    cxc_balance = fields.Monetary(
        string="Saldo CXC",
        compute="_compute_cxc_balance",
        currency_field="company_currency_id",
        readonly=True,
    )
    value_crc = fields.Float(string="Valor CRC", digits=(16, 2), readonly=True)
    value_usd = fields.Float(string="Valor USD", digits=(16, 2), readonly=True)

    def _get_context_wizard(self):
        wizard_id = self.env.context.get("sng_reporte_cons_wizard_id")
        if not wizard_id and self:
            wizard_id = self[0].wizard_id.id
        wizard = self.env["sng.reporte.cons.wizard"].browse(wizard_id).exists()
        if not wizard:
            raise UserError("No se encontró el asistente asociado a este reporte.")
        return wizard

    def action_download_report(self):
        return self._get_context_wizard().action_download()

    def action_open_filters(self):
        return self._get_context_wizard().action_open_wizard()

    @api.depends("partner_id", "company_id")
    def _compute_cxc_balance(self):
        for line in self:
            line.cxc_balance = 0.0

        lines_by_company = {}
        for line in self.filtered(lambda report_line: report_line.partner_id and report_line.company_id):
            lines_by_company.setdefault(line.company_id.id, self.env[self._name])
            lines_by_company[line.company_id.id] |= line

        for company_id, lines in lines_by_company.items():
            commercial_partners = lines.mapped("partner_id.commercial_partner_id")
            self.env.cr.execute("""
                SELECT
                    aml.partner_id,
                    COALESCE(SUM(aml.amount_residual), 0.0) AS cxc_balance
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN account_account aa ON aa.id = aml.account_id
                WHERE aa.account_type = 'asset_receivable'
                  AND am.state = 'posted'
                  AND aml.company_id = %s
                  AND aml.partner_id = ANY(%s)
                  AND aml.reconciled IS NOT TRUE
                GROUP BY aml.partner_id
            """, [company_id, commercial_partners.ids])
            balances = {
                partner_id: float(balance or 0.0)
                for partner_id, balance in self.env.cr.fetchall()
            }
            for line in lines:
                line.cxc_balance = balances.get(line.partner_id.commercial_partner_id.id, 0.0)


class SngReporteConsWizard(models.TransientModel):
    _name = "sng.reporte.cons.wizard"
    _description = "Wizard Reporte Consignaciones"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    partner_ids = fields.Many2many(
        "res.partner",
        "sng_reporte_cons_wiz_partner_rel",
        "wizard_id",
        "partner_id",
        string="Clientes",
        domain="[('sale_location_id', '!=', False)]",
    )
    salesperson_ids = fields.Many2many(
        "res.partner",
        "sng_reporte_cons_wiz_seller_rel",
        "wizard_id",
        "partner_id",
        string="Vendedores",
        domain="[('is_salesperson', '=', True)]",
    )
    line_ids = fields.One2many(
        "sng.reporte.cons.line", "wizard_id", string="Resultados", readonly=True
    )
    report_file = fields.Binary(string="Archivo", readonly=True)
    report_filename = fields.Char(string="Nombre archivo", readonly=True)

    def action_generate(self):
        self.ensure_one()
        domain = [
            ("sale_location_id", "!=", False),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.company_id.id),
        ]
        if self.partner_ids:
            domain.append(("id", "in", self.partner_ids.ids))
        if self.salesperson_ids:
            domain.append(("assigned_salesperson_id", "in", self.salesperson_ids.ids))

        partners = self.env["res.partner"].sudo().with_company(self.company_id).search(domain)
        if not partners:
            raise UserError("No se encontraron clientes con ubicación de consignación para los filtros seleccionados.")

        crc_currency = self.env["res.currency"].sudo().search([("name", "=", "CRC")], limit=1)
        usd_currency = self.env["res.currency"].sudo().search([("name", "=", "USD")], limit=1)
        company_currency = self.company_id.currency_id
        today = fields.Date.today()
        line_commands = [(5, 0, 0)]
        for partner in partners:
            location = partner.sale_location_id
            location_ids = self._get_child_location_ids(location)
            if not location_ids:
                continue

            last_entry = self._get_last_entry_date(location_ids)
            last_sale = self._get_last_sale_date(location_ids)
            value_company = self._get_location_value(location_ids)

            value_crc = self._convert_amount(value_company, company_currency, crc_currency, today)
            value_usd = self._convert_amount(value_company, company_currency, usd_currency, today)

            line_commands.append((0, 0, {
                "partner_id": partner.id,
                "partner_code": partner.unique_id or "",
                "commercial_name": partner.commercial_name or "",
                "salesperson_id": partner.assigned_salesperson_id.id or False,
                "location_id": location.id,
                "last_entry_date": last_entry,
                "last_sale_date": last_sale,
                "value_crc": value_crc,
                "value_usd": value_usd,
            }))

        self.write({"line_ids": line_commands})

        if len(line_commands) <= 1:
            raise UserError("No se encontraron ubicaciones de consignación válidas para los clientes seleccionados.")

        return self.action_view_results()

    def action_view_results(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Reporte Consignaciones",
            "res_model": "sng.reporte.cons.line",
            "view_mode": "list,form",
            "views": [
                (self.env.ref("sng_reporte_cons.view_sng_reporte_cons_line_list").id, "list"),
                (self.env.ref("sng_reporte_cons.view_sng_reporte_cons_line_form").id, "form"),
            ],
            "search_view_id": self.env.ref("sng_reporte_cons.view_sng_reporte_cons_line_search").id,
            "domain": [("wizard_id", "=", self.id)],
            "context": {"sng_reporte_cons_wizard_id": self.id},
            "target": "current",
        }

    def action_open_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
            "context": dict(self.env.context, sng_reporte_cons_wizard_id=self.id),
        }

    def action_download(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Primero genere el reporte antes de descargar.")
        excel = self._generate_excel()
        filename = "reporte_consignaciones_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S")
        self.write({
            "report_file": base64.b64encode(excel),
            "report_filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=report_file&filename=%s&download=true"
                   % (self._name, self.id, filename),
            "target": "self",
        }

    # -------------------------------------------------------------------------
    # Helpers de datos
    # -------------------------------------------------------------------------

    def _get_child_location_ids(self, location):
        return self.env["stock.location"].sudo().search([
            ("id", "child_of", location.id),
            ("usage", "=", "internal"),
            ("company_id", "in", [False, self.company_id.id]),
        ]).ids

    def _get_last_entry_date(self, location_ids):
        self.env.cr.execute("""
            SELECT MAX(sml.date)
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            WHERE sml.location_dest_id = ANY(%s)
              AND sm.state = 'done'
        """, [list(location_ids)])
        row = self.env.cr.fetchone()
        return row[0] if row else False

    def _get_last_sale_date(self, location_ids):
        self.env.cr.execute("""
            SELECT MAX(sml.date)
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            WHERE sml.location_id = ANY(%s)
              AND sm.state = 'done'
              AND sm.sale_line_id IS NOT NULL
        """, [list(location_ids)])
        row = self.env.cr.fetchone()
        return row[0] if row else False

    def _get_location_value(self, location_ids):
        self.env.cr.execute("""
            SELECT COALESCE(SUM(sq.quantity * pt.list_price), 0.0)
            FROM stock_quant sq
            JOIN product_product pp ON pp.id = sq.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sq.location_id = ANY(%s)
              AND sq.quantity > 0
        """, [list(location_ids)])
        row = self.env.cr.fetchone()
        return float(row[0]) if row and row[0] else 0.0

    def _convert_amount(self, amount, from_currency, to_currency, date):
        if not to_currency or not from_currency or amount == 0.0:
            return amount
        if from_currency == to_currency:
            return amount
        try:
            return from_currency._convert(amount, to_currency, self.company_id, date)
        except Exception:
            return amount

    # -------------------------------------------------------------------------
    # Excel
    # -------------------------------------------------------------------------

    def _generate_excel(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#4472C4", "color": "white",
            "align": "center", "valign": "vcenter", "border": 1,
        })
        text_fmt = workbook.add_format({"align": "left", "valign": "vcenter"})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm", "align": "center", "valign": "vcenter"})
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "align": "right", "valign": "vcenter"})

        ws = workbook.add_worksheet("Reporte")
        ws.freeze_panes(2, 0)

        generated_at = fields.Datetime.context_timestamp(
            self, fields.Datetime.now()
        ).replace(tzinfo=None)
        ws.write(0, 0, "Fecha y hora generación", header_fmt)
        ws.write_datetime(0, 1, generated_at, date_fmt)

        headers = [
            "Código", "Nombre Comercial", "Ruta", "Vendedor", "Nombre",
            "U Entrada", "U Venta", "Saldo CXC", "Valor CRC", "Valor USD",
        ]
        col_widths = [12, 32, 24, 28, 38, 20, 20, 18, 18, 18]
        for col, (header, width) in enumerate(zip(headers, col_widths)):
            ws.write(1, col, header, header_fmt)
            ws.set_column(col, col, width)

        for row_idx, line in enumerate(self.line_ids, start=2):
            ws.write(row_idx, 0, line.partner_code or "", text_fmt)
            ws.write(row_idx, 1, line.commercial_name or "", text_fmt)
            ws.write(row_idx, 2, line.sales_route_id.name or "", text_fmt)
            ws.write(row_idx, 3, line.salesperson_id.name or "", text_fmt)
            ws.write(row_idx, 4, line.location_id.complete_name or "", text_fmt)
            if line.last_entry_date:
                ws.write_datetime(row_idx, 5, line.last_entry_date.replace(tzinfo=None), date_fmt)
            else:
                ws.write(row_idx, 5, "", text_fmt)
            if line.last_sale_date:
                ws.write_datetime(row_idx, 6, line.last_sale_date.replace(tzinfo=None), date_fmt)
            else:
                ws.write(row_idx, 6, "", text_fmt)
            ws.write(row_idx, 7, line.cxc_balance, money_fmt)
            ws.write(row_idx, 8, line.value_crc, money_fmt)
            ws.write(row_idx, 9, line.value_usd, money_fmt)

        workbook.close()
        output.seek(0)
        return output.read()
