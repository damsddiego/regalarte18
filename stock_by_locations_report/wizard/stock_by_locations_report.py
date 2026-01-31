import io
import json
from odoo import fields, models, _, api
from odoo.tools import groupby, json_default
from odoo.exceptions import ValidationError


try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class StockLocation(models.TransientModel):
    _name = "stock.by.locations.report"
    _description = "Stock By Locations Report Wizard"

    report_format = fields.Selection([
        ('xlsx', 'XLSX'),
        ('pdf', 'PDF')
    ], string="Report Format", default='xlsx',
        help="Choose the report format")
    report_on = fields.Selection([
        ('all_products', 'All Products'),
        ('products_by_selection', 'Products By Selection')
    ], string="Report On", default='all_products',
        help="Select all products or by selection")
    product_ids = fields.Many2many('product.product',
                                         string="Products",
                                         help="Select the products you want to display in the report.")
    
    # Many2many field referencing res.company
    companies = fields.Many2many(
        'res.company', string='Companies', domain=lambda self: [('id', 'in', self._context.get('allowed_company_ids', []))],
         help="Select the companies you want to view the report for.")
    
    locations = fields.Many2many('stock.location', string="Locations", 
                                  required=True, help="Select the locations for which you want to view the report.")
    measures = fields.Many2many('measure.option', string='Measures',
                                  required=True, help="Select the measures that you want to display in the report.")

    @api.model
    def default_get(self, fields):
        """Sets the measures."""
        res = super(StockLocation, self).default_get(fields)
         # Fetch all measure options
        measure_options = self.env['measure.option'].search([])
        res.update({
            'companies': [(6, 0, self.env.companies.ids)],
            'measures': [(6, 0, measure_options.ids)]  # Set all measure options as default
        })
        return res
    
    @api.onchange('companies')
    def _onchange_companies(self):
        """ Update locations based on selected companies. """
        if self.companies:
            # Fetch all locations associated with the selected companies
            locations = self.env['stock.location'].search([
                ('company_id', 'in', self.companies.ids),
                ('usage', '=', 'internal')  # Only internal locations
                ])
            self.locations = locations
        else:
            self.locations = False

    @api.constrains('report_on', 'product_ids')
    def _check_product_ids_required(self):
        for record in self:
            if record.report_on == 'products_by_selection' and not record.product_ids:
                raise ValidationError("The 'Products' field is required when 'Products By Selection' is selected.")


    def action_print_report(self):
        if self.report_format == "xlsx":
            """ To print the XLSX report type"""
            if self.report_on == 'products_by_selection':
                query = self.env[
                    'report.stock_by_locations_report.report_stock_locations'].query_data(
                    self.report_on, self.product_ids.ids, self.locations.ids, self.measures.ids)
            else:
                product_ids = self.env['product.product'].search([]).ids
                query = self.env[
                    'report.stock_by_locations_report.report_stock_locations'].query_data(
                    self.report_on, product_ids, self.locations.ids, self.measures.ids)
            data = {
                'report_on': self.report_on,
                'product_ids': self.product_ids,
                'locations': self.locations,
                'measures': self.measures.ids,
                'var': query
            }
            return {
                'type': 'ir.actions.report',
                'data': {'model': 'stock.by.locations.report',
                        'options': json.dumps(data, default=json_default),
                        'output_format': 'xlsx',
                        'report_name': 'Stock By Locations Report',
                        },
                'report_type': 'xlsx',
            }
        else:
            if self.report_on == 'products_by_selection':
                product_ids = self.product_ids.ids
            else:
                product_ids = self.env['product.product'].search([]).ids
            """ To pass values in wizard"""
            data = {
                'report_on': self.report_on,
                'product_ids': product_ids,
                'locations': self.locations.ids,
                'measures': self.measures.ids,
            }
            return self.env.ref(
                'stock_by_locations_report.stock_by_locations_report').report_action(
                None, data=data)
        
    
    def get_xlsx_report(self, data, response):
        """To get the report values for xlsx report"""
        query_result = data['var']
        grouped_data = {}
        for product_id, group in groupby(query_result, key=lambda x: x['product']):
            grouped_data[product_id] = list(group)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet()

        # Cell formats
        cell_format = workbook.add_format({'font_size': 13, 'bold': True, 'align': 'right'})
        grey_cell_format = workbook.add_format({'bold': True, 'bg_color': '#99dfe7', 'align': 'center'})
        grey_cell_format_left_header = workbook.add_format({'bold': True, 'bg_color': '#99b0e7', 'align': 'left','font_size': 13})
        grey_cell_format_left = workbook.add_format({'bold': True, 'bg_color': '#99dfe7', 'align': 'left','font_size': 12})
        grey_cell_format_right = workbook.add_format({'bold': True, 'bg_color': '#99dfe7', 'align': 'right','font_size': 12})
        head = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'bold': True, 'font_size': 20, 'bg_color': '#0a79c2'})
        txt = workbook.add_format({'font_size': 12, 'align': 'left'})
        txt_right = workbook.add_format({'font_size': 12, 'align': 'right'})
        txt_head = workbook.add_format({'font_size': 10, 'align': 'left', 'bold': True})

        # Set column widths
        sheet.set_column(0, 0, 50)
        sheet.set_column(1, 1, 25)
        sheet.set_column(2, 2, 17)
        sheet.set_column(3, 3, 17)
        sheet.set_column(4, 4, 17)
        sheet.set_column(5, 5, 17)
        sheet.set_column(6, 6, 17)
        sheet.set_column(7, 7, 17)

        
        # Merge ranges and write headers
        sheet.merge_range('A2:H3', 'STOCK BY LOCATIONS REPORT', head)

        sheet.write(3, 0, 'Report Date: ' + str(fields.Date.today()), txt_head)

        # Write column headers
        headers = ['Product', 'Location']

        measure_records = self.env['measure.option'].browse(data['measures'])

        # Create a set to hold the measure IDs
        measure_ids = {measure.id for measure in measure_records}

        # Append headers based on presence of measure IDs
        if 1 in measure_ids:
            headers.append('On Hand Qty')
        if 2 in measure_ids:
            headers.append('Free To Use Qty')
        if 3 in measure_ids:
            headers.append('Reserved Qty')
        if 4 in measure_ids:
            headers.append('Forecast Qty')
        if 5 in measure_ids:
            headers.append('Incoming Qty')
        if 6 in measure_ids:
            headers.append('Outgoing Qty')
            
        for col_num, header in enumerate(headers):
            sheet.write(5, col_num, header, grey_cell_format_left_header)

        row = 6
        for product_id, product_data in grouped_data.items():
            for data in product_data:
                sheet.write(row, 0, product_id, txt)
                sheet.write(row, 1, data['location'], txt) 

                col = 2
                if 1 in measure_ids:
                    sheet.write(row, col, data['on_hand_qty'], txt_right)
                    col += 1
                if 2 in measure_ids:
                    sheet.write(row, col, data['qty_free'], txt_right)
                    col += 1
                if 3 in measure_ids:
                    sheet.write(row, col, data['qty_reserved'], txt_right)
                    col += 1
                if 4 in measure_ids:
                    sheet.write(row, col, data['forecast_qty'], txt_right)
                    col += 1
                if 5 in measure_ids:
                    sheet.write(row, col, data['qty_incoming'], txt_right)
                    col += 1
                if 6 in measure_ids:
                    sheet.write(row, col, data['qty_outgoing'], txt_right)
                row += 1
            
            # Write totals
            sheet.write(row, 0, 'Total: ' + product_id, grey_cell_format_left)
            sheet.write(row, 1, '', grey_cell_format_left)
            
            col_s = 2
            if 1 in measure_ids:
                sheet.write(row, col_s, sum(x['on_hand_qty'] for x in product_data), grey_cell_format_right)
                col_s += 1
            if 2 in measure_ids:
                sheet.write(row, col_s, sum(x['qty_free'] for x in product_data), grey_cell_format_right)
                col_s += 1
            if 3 in measure_ids:
                sheet.write(row, col_s, sum(x['qty_reserved'] for x in product_data), grey_cell_format_right)
                col_s += 1
            if 4 in measure_ids:
                sheet.write(row, col_s, sum(x['forecast_qty'] for x in product_data), grey_cell_format_right)
                col_s += 1
            if 5 in measure_ids:
                sheet.write(row, col_s, sum(x['qty_incoming'] for x in product_data), grey_cell_format_right)
                col_s += 1
            if 6 in measure_ids:
                sheet.write(row, col_s, sum(x['qty_outgoing'] for x in product_data), grey_cell_format_right)
            row += 1
        
        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
