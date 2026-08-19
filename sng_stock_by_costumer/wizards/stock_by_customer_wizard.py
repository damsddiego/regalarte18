# -*- coding: utf-8 -*-

import base64
import io
import logging
from collections import defaultdict
from datetime import datetime, time

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class StockByCustomerWizardLine(models.TransientModel):
    _name = 'stock.by.customer.wizard.line'
    _description = 'Stock by Customer Report Line'
    _order = 'total_amount desc, partner_id, product_id, location_id'

    wizard_id = fields.Many2one('stock.by.customer.wizard', ondelete='cascade')
    company_id = fields.Many2one('res.company', related='wizard_id.company_id', store=True, readonly=True)
    date_report = fields.Date(related='wizard_id.date_report', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id', store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    partner_ref = fields.Char(string='Código', readonly=True)
    salesperson_id = fields.Many2one('res.partner', string='Vendedor', readonly=True)
    root_location_id = fields.Many2one('stock.location', string='Ubicación Cliente', readonly=True)
    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    product_default_code = fields.Char(string='Código Producto', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UdM', readonly=True)
    quantity = fields.Float(string='Cantidad', digits=(16, 2), readonly=True)
    unit_price = fields.Monetary(string='Precio Venta', currency_field='currency_id', readonly=True)
    subtotal_amount = fields.Monetary(string='Subtotal', currency_field='currency_id', readonly=True)
    tax_amount = fields.Monetary(string='Impuesto', currency_field='currency_id', readonly=True)
    total_amount = fields.Monetary(string='Total', currency_field='currency_id', readonly=True)
    is_zero_stock_line = fields.Boolean(string='Sin Stock', readonly=True)

    def _get_context_wizard(self):
        wizard_id = self.env.context.get('stock_by_customer_wizard_id')
        if not wizard_id and self:
            wizard_id = self[0].wizard_id.id
        wizard = self.env['stock.by.customer.wizard'].browse(wizard_id).exists()
        if not wizard:
            raise UserError('No se encontró el asistente asociado a este reporte.')
        return wizard

    def action_download_report(self):
        wizard = self._get_context_wizard()
        return wizard.action_download()

    def action_open_filters(self):
        wizard = self._get_context_wizard()
        return wizard.action_open_wizard()


class StockByCustomerWizard(models.TransientModel):
    _name = 'stock.by.customer.wizard'
    _description = 'Stock by Customer Report Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
    )
    date_report = fields.Date(
        string='Fecha del Reporte',
        default=fields.Date.context_today,
        required=True,
    )
    include_zero_stock = fields.Boolean(
        string='Incluir Clientes sin Stock',
        default=False,
    )

    # --- Filtros opcionales ---
    partner_ids = fields.Many2many(
        'res.partner',
        'stock_by_cust_wiz_partner_rel',
        'wizard_id', 'partner_id',
        string='Clientes',
        domain="[('sale_location_id', '!=', False)]",
        help="Dejar vacío para incluir todos los clientes con ubicación asignada",
    )
    salesperson_ids = fields.Many2many(
        'res.partner',
        'stock_by_cust_wiz_seller_rel',
        'wizard_id', 'partner_id',
        string='Vendedores',
        domain="[('is_salesperson', '=', True)]",
        help="Filtrar por vendedor asignado al cliente",
    )
    location_ids = fields.Many2many(
        'stock.location',
        'stock_by_cust_wiz_location_rel',
        'wizard_id', 'location_id',
        string='Ubicaciones',
        domain="[('usage', '=', 'internal')]",
        help="Dejar vacío para incluir todas las ubicaciones",
    )
    product_ids = fields.Many2many(
        'product.product',
        'stock_by_cust_wiz_product_rel',
        'wizard_id', 'product_id',
        string='Productos',
        domain="[('is_storable', '=', True)]",
        help="Dejar vacío para incluir todos los productos",
    )

    report_file = fields.Binary(string='Archivo', readonly=True)
    report_filename = fields.Char(string='Nombre de archivo', readonly=True)
    line_ids = fields.One2many(
        'stock.by.customer.wizard.line',
        'wizard_id',
        string='Resultados',
        readonly=True,
    )

    def action_generate_report(self):
        self.ensure_one()
        cutoff_dt = self._get_cutoff_datetime()
        partners = self._get_report_partners()

        if not partners:
            raise UserError('No se encontraron clientes con ubicación de venta asignada para los filtros seleccionados.')

        _logger.info("Found %d partners matching filters", len(partners))
        summary_rows, detail_rows, line_commands = self._build_report_snapshot(partners, cutoff_dt)

        if not summary_rows:
            raise UserError(
                'Se encontraron %d clientes con los filtros aplicados, pero ninguno tiene productos en stock.\n'
                'Active "Incluir Clientes sin Stock" para verlos de todas formas.' % len(partners)
            )

        excel_file = self._generate_excel(summary_rows, detail_rows)
        filename = 'stock_by_customer_%s.xlsx' % datetime.now().strftime('%Y%m%d_%H%M%S')

        self.write({
            'report_file': base64.b64encode(excel_file),
            'report_filename': filename,
            'line_ids': [(5, 0, 0)] + line_commands,
        })
        return self.action_view_results()

    def action_view_results(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock por Cliente',
            'res_model': 'stock.by.customer.wizard.line',
            'view_mode': 'list,pivot,graph,form',
            'views': [
                (self.env.ref('sng_stock_by_costumer.view_stock_by_customer_line_list').id, 'list'),
                (self.env.ref('sng_stock_by_costumer.view_stock_by_customer_line_pivot').id, 'pivot'),
                (self.env.ref('sng_stock_by_costumer.view_stock_by_customer_line_graph').id, 'graph'),
                (self.env.ref('sng_stock_by_costumer.view_stock_by_customer_line_form').id, 'form'),
            ],
            'search_view_id': self.env.ref('sng_stock_by_costumer.view_stock_by_customer_line_search').id,
            'domain': [('wizard_id', '=', self.id)],
            'context': {
                'search_default_group_partner': 1,
                'stock_by_customer_wizard_id': self.id,
                'pivot_measures': ['quantity', 'subtotal_amount', 'tax_amount', 'total_amount'],
            },
            'target': 'current',
        }

    def action_open_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': dict(self.env.context, stock_by_customer_wizard_id=self.id),
        }

    def _get_cutoff_datetime(self):
        report_date = fields.Date.to_date(self.date_report)
        return datetime.combine(report_date, time.max)

    def _get_report_partners(self):
        domain = [
            ('sale_location_id', '!=', False),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ]

        if self.partner_ids:
            domain.append(('id', 'in', self.partner_ids.ids))

        if self.salesperson_ids:
            domain.append(('assigned_salesperson_id', 'in', self.salesperson_ids.ids))

        if self.location_ids:
            domain.append(('sale_location_id', 'in', self.location_ids.ids))

        return self.env['res.partner'].with_company(self.company_id).search(domain)

    def _build_report_snapshot(self, partners, cutoff_dt):
        summary_rows = []
        detail_rows = []
        line_commands = []
        product_filter_ids = set(self.product_ids.ids)

        for partner in partners:
            root_location = partner.sale_location_id
            location_ids = self._get_internal_child_location_ids(root_location)
            qty_map = self._get_qty_map(location_ids, cutoff_dt, product_filter_ids)

            total_quantity = 0.0
            subtotal_amount = 0.0
            tax_amount = 0.0
            total_amount = 0.0
            product_ids = set()
            detail_count = 0
            salesperson = partner.assigned_salesperson_id

            for (product_id, location_id), quantity in sorted(qty_map.items(), key=lambda item: item[0]):
                product = self.env['product.product'].browse(product_id)
                unit_price = product.with_company(self.company_id).list_price or 0.0
                taxes = product.taxes_id.filtered(
                    lambda tax: not tax.company_id or tax.company_id == self.company_id
                )
                totals = taxes.compute_all(
                    unit_price,
                    currency=self.company_id.currency_id,
                    quantity=quantity,
                    product=product,
                    partner=partner,
                )
                line_subtotal = totals['total_excluded']
                line_total = totals['total_included']
                line_tax = line_total - line_subtotal

                total_quantity += quantity
                subtotal_amount += line_subtotal
                tax_amount += line_tax
                total_amount += line_total
                product_ids.add(product_id)
                detail_count += 1

                detail_rows.append({
                    'partner_ref': getattr(partner, 'unique_id', False) or '',
                    'partner_name': partner.name,
                    'salesperson_name': salesperson.name if salesperson else '',
                    'root_location_name': root_location.complete_name,
                    'location_name': self.env['stock.location'].browse(location_id).complete_name,
                    'product_code': product.default_code or '',
                    'product_name': product.display_name,
                    'quantity': quantity,
                    'uom': product.uom_id.name,
                    'unit_price': unit_price,
                    'subtotal_amount': line_subtotal,
                    'tax_amount': line_tax,
                    'total_amount': line_total,
                })
                line_commands.append((0, 0, {
                    'partner_id': partner.id,
                    'partner_ref': getattr(partner, 'unique_id', False) or '',
                    'salesperson_id': salesperson.id if salesperson else False,
                    'root_location_id': root_location.id,
                    'location_id': location_id,
                    'product_id': product.id,
                    'product_default_code': product.default_code or '',
                    'uom_id': product.uom_id.id,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'subtotal_amount': line_subtotal,
                    'tax_amount': line_tax,
                    'total_amount': line_total,
                    'is_zero_stock_line': False,
                }))

            if detail_count == 0 and not self.include_zero_stock:
                continue

            if detail_count == 0:
                line_commands.append((0, 0, {
                    'partner_id': partner.id,
                    'partner_ref': getattr(partner, 'unique_id', False) or '',
                    'salesperson_id': salesperson.id if salesperson else False,
                    'root_location_id': root_location.id,
                    'location_id': root_location.id,
                    'product_id': False,
                    'product_default_code': '',
                    'uom_id': False,
                    'quantity': 0.0,
                    'unit_price': 0.0,
                    'subtotal_amount': 0.0,
                    'tax_amount': 0.0,
                    'total_amount': 0.0,
                    'is_zero_stock_line': True,
                }))

            partner_balance = partner.with_company(self.company_id).credit
            summary_rows.append({
                'partner_ref': getattr(partner, 'unique_id', False) or '',
                'partner_name': partner.name,
                'salesperson_name': salesperson.name if salesperson else '',
                'location_name': root_location.complete_name,
                'product_count': len(product_ids),
                'total_quantity': total_quantity,
                'subtotal_amount': subtotal_amount,
                'tax_amount': tax_amount,
                'total_amount': total_amount,
                'partner_balance': partner_balance,
                'final_balance': total_amount + partner_balance,
            })

        summary_rows.sort(key=lambda row: row['total_amount'], reverse=True)
        detail_rows.sort(key=lambda row: (row['partner_name'], row['location_name'], row['product_name']))
        return summary_rows, detail_rows, line_commands

    def _get_internal_child_location_ids(self, location):
        return self.env['stock.location'].search([
            ('id', 'child_of', location.id),
            ('usage', '=', 'internal'),
            ('company_id', 'in', [False, self.company_id.id]),
        ]).ids

    def _get_qty_map(self, location_ids, cutoff_dt, product_filter_ids):
        qty_map = defaultdict(float)
        Quant = self.env['stock.quant'].with_company(self.company_id)
        quant_domain = [
            ('location_id', 'in', location_ids),
            ('quantity', '!=', 0),
        ]
        if product_filter_ids:
            quant_domain.append(('product_id', 'in', list(product_filter_ids)))

        grouped_quants = Quant.read_group(
            quant_domain,
            ['quantity:sum'],
            ['location_id', 'product_id'],
            lazy=False,
        )
        for row in grouped_quants:
            location = row.get('location_id')
            product = row.get('product_id')
            quantity = row.get('quantity', row.get('quantity_sum', 0.0))
            if location and product:
                qty_map[(product[0], location[0])] += quantity

        now_dt = fields.Datetime.now()
        if cutoff_dt < now_dt:
            location_set = set(location_ids)
            move_domain = [
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'done'),
                ('date', '>', fields.Datetime.to_string(cutoff_dt)),
                '|', ('location_id', 'in', location_ids), ('location_dest_id', 'in', location_ids),
            ]
            if product_filter_ids:
                move_domain.append(('product_id', 'in', list(product_filter_ids)))

            future_move_lines = self.env['stock.move.line'].with_company(self.company_id).search(move_domain)
            for move_line in future_move_lines:
                quantity = move_line.quantity or 0.0
                if move_line.location_dest_id.id in location_set:
                    qty_map[(move_line.product_id.id, move_line.location_dest_id.id)] -= quantity
                if move_line.location_id.id in location_set:
                    qty_map[(move_line.product_id.id, move_line.location_id.id)] += quantity

        cleaned_qty_map = {}
        products = self.env['product.product'].browse(list({key[0] for key in qty_map}))
        rounding_by_product = {
            product.id: product.uom_id.rounding or 0.01
            for product in products
        }
        for key, quantity in qty_map.items():
            rounding = rounding_by_product.get(key[0], 0.01)
            if not float_is_zero(quantity, precision_rounding=rounding):
                cleaned_qty_map[key] = quantity
        return cleaned_qty_map

    def _generate_excel(self, summary_rows, detail_rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#4472C4', 'color': 'white',
            'align': 'center', 'valign': 'vcenter', 'border': 1,
        })
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
        })
        currency_fmt = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        number_fmt = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        text_fmt = workbook.add_format({'align': 'left'})

        # --- Hoja Resumen ---
        ws = workbook.add_worksheet('Resumen')
        ws.set_column('A:A', 15)
        ws.set_column('B:B', 28)
        ws.set_column('C:C', 20)
        ws.set_column('D:D', 15)
        ws.set_column('E:E', 15)
        ws.set_column('F:F', 18)
        ws.set_column('G:G', 18)
        ws.set_column('H:H', 18)
        ws.set_column('I:I', 18)
        ws.set_column('J:J', 18)

        ws.merge_range('A1:J1', 'REPORTE DE INVENTARIO POR CLIENTE', title_fmt)
        ws.write('A2', f'Compañía: {self.company_id.name}')
        ws.write('A3', f'Fecha: {self.date_report.strftime("%d/%m/%Y")}')

        row = 4
        for col, label in enumerate(['Código', 'Cliente', 'Vendedor', 'Ubicación',
                                      'Cant. Productos', 'Cant. Total', 'Subtotal',
                                      'Impuesto', 'Total', 'Saldo C×C', 'Saldo Final']):
            ws.write(row, col, label, header_fmt)
        ws.set_column('K:K', 18)

        row += 1
        grand_subtotal = 0.0
        grand_tax = 0.0
        grand_total = 0.0
        grand_balance = 0.0
        grand_final = 0.0
        for item in summary_rows:
            final = item['final_balance']
            ws.write(row, 0, item['partner_ref'], text_fmt)
            ws.write(row, 1, item['partner_name'], text_fmt)
            ws.write(row, 2, item['salesperson_name'], text_fmt)
            ws.write(row, 3, item['location_name'], text_fmt)
            ws.write(row, 4, item['product_count'], number_fmt)
            ws.write(row, 5, item['total_quantity'], number_fmt)
            ws.write(row, 6, item['subtotal_amount'], currency_fmt)
            ws.write(row, 7, item['tax_amount'], currency_fmt)
            ws.write(row, 8, item['total_amount'], currency_fmt)
            ws.write(row, 9, item['partner_balance'], currency_fmt)
            ws.write(row, 10, final, currency_fmt)
            grand_subtotal += item['subtotal_amount']
            grand_tax += item['tax_amount']
            grand_total += item['total_amount']
            grand_balance += item['partner_balance']
            grand_final += final
            row += 1

        row += 1
        ws.write(row, 5, 'TOTAL GENERAL:', header_fmt)
        ws.write(row, 6, grand_subtotal, currency_fmt)
        ws.write(row, 7, grand_tax, currency_fmt)
        ws.write(row, 8, grand_total, currency_fmt)
        ws.write(row, 9, grand_balance, currency_fmt)
        ws.write(row, 10, grand_final, currency_fmt)

        # --- Hoja Detalle ---
        wd = workbook.add_worksheet('Detalle por Producto')
        wd.set_column('A:A', 15)
        wd.set_column('B:B', 25)
        wd.set_column('C:C', 15)
        wd.set_column('D:D', 35)
        wd.set_column('E:E', 12)
        wd.set_column('F:F', 8)
        wd.set_column('G:G', 15)
        wd.set_column('H:H', 15)
        wd.set_column('I:I', 15)
        wd.set_column('J:J', 15)
        wd.set_column('K:K', 35)

        wd.merge_range('A1:K1', 'DETALLE DE PRODUCTOS POR CLIENTE', title_fmt)

        row = 3
        for col, label in enumerate(['Código', 'Cliente', 'Código Producto', 'Producto',
                                      'Cantidad', 'UdM', 'Precio Venta', 'Subtotal', 'Impuesto', 'Total', 'Ubicación']):
            wd.write(row, col, label, header_fmt)

        row += 1
        for item in detail_rows:
            wd.write(row, 0, item['partner_ref'], text_fmt)
            wd.write(row, 1, item['partner_name'], text_fmt)
            wd.write(row, 2, item['product_code'], text_fmt)
            wd.write(row, 3, item['product_name'], text_fmt)
            wd.write(row, 4, item['quantity'], number_fmt)
            wd.write(row, 5, item['uom'], text_fmt)
            wd.write(row, 6, item['unit_price'], currency_fmt)
            wd.write(row, 7, item['subtotal_amount'], currency_fmt)
            wd.write(row, 8, item['tax_amount'], currency_fmt)
            wd.write(row, 9, item['total_amount'], currency_fmt)
            wd.write(row, 10, item['location_name'], text_fmt)
            row += 1

        workbook.close()
        output.seek(0)
        return output.read()

    def action_download(self):
        self.ensure_one()
        if not self.report_file:
            raise UserError('Primero genere el reporte antes de descargar el archivo.')
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=report_file&filename={self.report_filename}&download=true',
            'target': 'self',
        }
