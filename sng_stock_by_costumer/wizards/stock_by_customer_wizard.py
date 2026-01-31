# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import base64
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class StockByCustomerWizard(models.TransientModel):
    _name = 'stock.by.customer.wizard'
    _description = 'Stock by Customer Report Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    date_report = fields.Date(
        string='Report Date',
        default=fields.Date.context_today,
        required=True,
        help="Calculate inventory value as of this date"
    )

    include_zero_stock = fields.Boolean(
        string='Include Customers with Zero Stock',
        default=False,
        help="Include customers even if they have no inventory in their location"
    )

    report_file = fields.Binary(
        string='Report File',
        readonly=True
    )

    report_filename = fields.Char(
        string='Filename',
        readonly=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')
    ], default='draft')

    def action_generate_report(self):
        """Generate the Excel report with stock by customer"""
        self.ensure_one()

        # Get all partners and filter those with assigned stock location
        # sale_location_id is the custom field that stores the sales location
        all_partners = self.env['res.partner'].with_company(self.company_id).search([
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)
        ])

        partners = all_partners.filtered(lambda p: p.sale_location_id)

        if not partners:
            raise UserError('No se encontraron clientes con ubicación de venta asignada.')

        _logger.info("Found %d partners with sale_location_id", len(partners))

        # Prepare data
        report_data = []
        Location = self.env['stock.location']
        Quant = self.env['stock.quant']

        for partner in partners:
            location = partner.sale_location_id

            if not location:
                continue

            _logger.info("Processing partner: %s (ID: %d) - Location: %s (ID: %d, Type: %s)",
                        partner.name, partner.id, location.complete_name, location.id, location.usage)

            # Get location and all child locations
            location_ids = Location.search([
                ('id', 'child_of', location.id),
                ('company_id', 'in', [False, self.company_id.id])
            ]).ids

            _logger.info("Found %d locations (including children) for partner %s", len(location_ids), partner.name)

            # Get all quants in these locations (removed strict company_id filter)
            quants = Quant.search([
                ('location_id', 'in', location_ids),
                ('quantity', '>', 0)
            ])

            _logger.info("Found %d quants with positive quantity for partner %s", len(quants), partner.name)

            # Calculate total value
            total_value = 0.0
            total_quantity = 0.0
            product_count = 0
            product_details = []

            for quant in quants:
                if quant.quantity > 0:
                    product = quant.product_id
                    unit_price = product.list_price or 0.0  # Precio de venta
                    value = quant.quantity * unit_price

                    total_quantity += quant.quantity
                    total_value += value
                    product_count += 1

                    product_details.append({
                        'product_code': product.default_code or '',
                        'product_name': product.name,
                        'quantity': quant.quantity,
                        'uom': product.uom_id.name,
                        'unit_price': unit_price,
                        'total_value': value,
                        'location_name': quant.location_id.complete_name
                    })

            # Skip if no products found (not based on value, since products might have zero cost)
            # Only skip if there are truly no products, unless user wants to see those too
            if product_count == 0 and not self.include_zero_stock:
                continue

            # Include this customer in the report
            if product_count > 0 or self.include_zero_stock:
                # Get customer balance (unpaid invoices)
                # The 'credit' field represents total receivable amount
                partner_balance = partner.credit
                
                report_data.append({
                    'partner_id': partner.id,
                    'partner_name': partner.name,
                    'partner_ref': partner.unique_id or '',
                    'location_id': location.id,
                    'location_name': location.complete_name,
                    'total_value': total_value,
                    'total_quantity': total_quantity,
                    'product_count': product_count,
                    'partner_balance': partner_balance,
                    'product_details': product_details
                })

        # Sort by total value descending
        report_data.sort(key=lambda x: x['total_value'], reverse=True)

        _logger.info("Report generated with %d customer records", len(report_data))

        if not report_data:
            raise UserError('Se encontraron %d clientes con ubicación de venta asignada, pero ninguno tiene productos en stock.\n\n'
                          'Posibles causas:\n'
                          '1. Las ubicaciones no tienen productos con cantidad > 0\n'
                          '2. Marca la opción "Include Customers with Zero Stock" para ver todos los clientes' % len(partners))

        # Generate Excel file
        excel_file = self._generate_excel(report_data)

        # Save file
        filename = 'stock_by_customer_%s.xlsx' % datetime.now().strftime('%Y%m%d_%H%M%S')

        self.write({
            'report_file': base64.b64encode(excel_file),
            'report_filename': filename,
            'state': 'done'
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context
        }

    def _generate_excel(self, data):
        """Generate Excel file with the report data"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter'
        })

        currency_format = workbook.add_format({
            'num_format': '#,##0.00',
            'align': 'right'
        })

        number_format = workbook.add_format({
            'num_format': '#,##0.00',
            'align': 'right'
        })

        text_format = workbook.add_format({
            'align': 'left'
        })

        # Summary sheet
        summary_sheet = workbook.add_worksheet('Resumen')
        summary_sheet.set_column('A:A', 15)  # Partner Ref
        summary_sheet.set_column('B:B', 30)  # Partner Name
        summary_sheet.set_column('C:C', 15)  # Product Count
        summary_sheet.set_column('D:D', 15)  # Total Quantity
        summary_sheet.set_column('E:E', 18)  # Total Value
        summary_sheet.set_column('F:F', 18)  # Customer Balance
        summary_sheet.set_column('G:G', 18)  # Final Balance

        # Title
        summary_sheet.merge_range('A1:G1', 'REPORTE DE INVENTARIO POR CLIENTE', title_format)
        summary_sheet.write('A2', f'Compañía: {self.company_id.name}')
        summary_sheet.write('A3', f'Fecha: {self.date_report.strftime("%d/%m/%Y")}')

        # Headers
        row = 4
        summary_sheet.write(row, 0, 'Código Cliente', header_format)
        summary_sheet.write(row, 1, 'Nombre Cliente', header_format)
        summary_sheet.write(row, 2, 'Cant. Productos', header_format)
        summary_sheet.write(row, 3, 'Cant. Total', header_format)
        summary_sheet.write(row, 4, 'Valor Total', header_format)
        summary_sheet.write(row, 5, 'Saldo Cliente', header_format)
        summary_sheet.write(row, 6, 'Saldo Final', header_format)

        # Data rows
        row += 1
        grand_total = 0.0

        for item in data:
            final_balance = item['total_value'] + item['partner_balance']
            
            summary_sheet.write(row, 0, item['partner_ref'], text_format)
            summary_sheet.write(row, 1, item['partner_name'], text_format)
            summary_sheet.write(row, 2, item['product_count'], number_format)
            summary_sheet.write(row, 3, item['total_quantity'], number_format)
            summary_sheet.write(row, 4, item['total_value'], currency_format)
            summary_sheet.write(row, 5, item['partner_balance'], currency_format)
            summary_sheet.write(row, 6, final_balance, currency_format)

            grand_total += item['total_value']
            row += 1

        # Grand total
        row += 1
        summary_sheet.write(row, 3, 'TOTAL GENERAL:', header_format)
        summary_sheet.write(row, 4, grand_total, currency_format)

        # Detail sheet
        detail_sheet = workbook.add_worksheet('Detalle por Producto')
        detail_sheet.set_column('A:A', 15)  # Partner Ref
        detail_sheet.set_column('B:B', 25)  # Partner Name
        detail_sheet.set_column('C:C', 15)  # Product Code
        detail_sheet.set_column('D:D', 35)  # Product Name
        detail_sheet.set_column('E:E', 12)  # Quantity
        detail_sheet.set_column('F:F', 8)   # UOM
        detail_sheet.set_column('G:G', 15)  # Unit Price
        detail_sheet.set_column('H:H', 15)  # Total Value

        # Title
        detail_sheet.merge_range('A1:H1', 'DETALLE DE PRODUCTOS POR CLIENTE', title_format)

        # Headers
        row = 3
        detail_sheet.write(row, 0, 'Código Cliente', header_format)
        detail_sheet.write(row, 1, 'Nombre Cliente', header_format)
        detail_sheet.write(row, 2, 'Código Producto', header_format)
        detail_sheet.write(row, 3, 'Producto', header_format)
        detail_sheet.write(row, 4, 'Cantidad', header_format)
        detail_sheet.write(row, 5, 'UdM', header_format)
        detail_sheet.write(row, 6, 'Precio Unitario', header_format)
        detail_sheet.write(row, 7, 'Valor Total', header_format)

        # Data rows
        row += 1
        for item in data:
            for product in item['product_details']:
                detail_sheet.write(row, 0, item['partner_ref'], text_format)
                detail_sheet.write(row, 1, item['partner_name'], text_format)
                detail_sheet.write(row, 2, product['product_code'], text_format)
                detail_sheet.write(row, 3, product['product_name'], text_format)
                detail_sheet.write(row, 4, product['quantity'], number_format)
                detail_sheet.write(row, 5, product['uom'], text_format)
                detail_sheet.write(row, 6, product['unit_price'], currency_format)
                detail_sheet.write(row, 7, product['total_value'], currency_format)
                row += 1

        workbook.close()
        output.seek(0)

        return output.read()

    def action_download(self):
        """Download the generated report"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=report_file&filename={self.report_filename}&download=true',
            'target': 'self',
        }
