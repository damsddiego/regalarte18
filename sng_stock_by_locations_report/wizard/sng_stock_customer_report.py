import io
import json
from odoo import fields, models, _, api
from odoo.tools import json_default
from odoo.exceptions import ValidationError

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class SngStockCustomerReport(models.TransientModel):
    _name = "sng.stock.customer.report"
    _description = "SNG Stock Customer Report Wizard"

    report_format = fields.Selection([
        ('xlsx', 'XLSX'),
        ('pdf', 'PDF')
    ], string="Report Format", default='xlsx',
        help="Choose the report format")

    report_on = fields.Selection([
        ('all_customers', 'All Customers'),
        ('customers_by_selection', 'Customers By Selection')
    ], string="Report On", default='all_customers',
        help="Select all customers or by selection")

    partner_ids = fields.Many2many(
        'res.partner',
        string="Customers",
        domain=[('customer_rank', '>', 0)],
        help="Select the customers you want to display in the report.")

    companies = fields.Many2many(
        'res.company',
        string='Companies',
        domain=lambda self: [('id', 'in', self._context.get('allowed_company_ids', []))],
        help="Select the companies you want to view the report for.")

    date_from = fields.Date(string="Date From", help="Filter stock from this date")
    date_to = fields.Date(string="Date To", default=fields.Date.today(), help="Filter stock up to this date")

    @api.model
    def default_get(self, fields):
        """Set default values."""
        res = super(SngStockCustomerReport, self).default_get(fields)
        res.update({
            'companies': [(6, 0, self.env.companies.ids)],
        })
        return res

    @api.constrains('report_on', 'partner_ids')
    def _check_partner_ids_required(self):
        for record in self:
            if record.report_on == 'customers_by_selection' and not record.partner_ids:
                raise ValidationError(
                    _("The 'Customers' field is required when 'Customers By Selection' is selected."))

    def action_print_report(self):
        """Generate the report based on selected format."""
        if self.report_on == 'customers_by_selection':
            partner_ids = self.partner_ids.ids
        else:
            partner_ids = self.env['res.partner'].search([('customer_rank', '>', 0)]).ids

        if self.report_format == "xlsx":
            # Query data for XLSX
            query = self.env['report.sng_stock_by_locations_report.report_stock_customer'].query_data(
                partner_ids, self.companies.ids, self.date_from, self.date_to)

            # Validate that we have data
            if not query:
                raise ValidationError(
                    _("No stock records found for the selected criteria.\n\n"
                      "Note: This report searches for stock in customer locations (usage='customer') "
                      "that have a partner assigned to the location.\n\n"
                      "If you want to see stock by customer based on property_stock_supplier, "
                      "please use the 'Stock by Customer' report instead."))

            data = {
                'report_on': self.report_on,
                'partner_ids': partner_ids,
                'companies': self.companies.ids,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'var': query
            }
            return {
                'type': 'ir.actions.report',
                'data': {
                    'model': 'sng.stock.customer.report',
                    'options': json.dumps(data, default=json_default),
                    'output_format': 'xlsx',
                    'report_name': 'Stock By Customer Location Report',
                },
                'report_type': 'xlsx',
            }
        else:
            # PDF report - validate data first
            query = self.env['report.sng_stock_by_locations_report.report_stock_customer'].query_data(
                partner_ids, self.companies.ids, self.date_from, self.date_to)

            if not query:
                raise ValidationError(
                    _("No stock records found for the selected criteria.\n\n"
                      "Note: This report searches for stock in customer locations (usage='customer') "
                      "that have a partner assigned to the location.\n\n"
                      "If you want to see stock by customer based on property_stock_supplier, "
                      "please use the 'Stock by Customer' report instead."))

            data = {
                'report_on': self.report_on,
                'partner_ids': partner_ids,
                'companies': self.companies.ids,
                'date_from': self.date_from,
                'date_to': self.date_to,
            }
            return self.env.ref(
                'sng_stock_by_locations_report.action_report_stock_customer').report_action(
                None, data=data)

    def get_xlsx_report(self, data, response):
        """Generate XLSX report."""
        query_result = data['var']

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Customer Stock Report')

        # Cell formats
        head = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
            'font_size': 20,
            'bg_color': '#0a79c2',
            'font_color': 'white'
        })
        header = workbook.add_format({
            'bold': True,
            'bg_color': '#99b0e7',
            'align': 'center',
            'font_size': 13,
            'border': 1
        })
        txt = workbook.add_format({
            'font_size': 12,
            'align': 'left',
            'border': 1
        })
        txt_right = workbook.add_format({
            'font_size': 12,
            'align': 'right',
            'border': 1
        })
        number_format = workbook.add_format({
            'font_size': 12,
            'align': 'right',
            'border': 1,
            'num_format': '#,##0.00'
        })
        total_format = workbook.add_format({
            'bold': True,
            'bg_color': '#99dfe7',
            'align': 'right',
            'font_size': 12,
            'border': 1,
            'num_format': '#,##0.00'
        })
        txt_info = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'bold': True
        })

        # Set column widths
        sheet.set_column(0, 0, 25)  # Unique ID
        sheet.set_column(1, 1, 40)  # Customer Name
        sheet.set_column(2, 2, 40)  # Location
        sheet.set_column(3, 3, 20)  # Total Quantity
        sheet.set_column(4, 4, 25)  # Total Value

        # Title
        sheet.merge_range('A2:E3', 'STOCK BY CUSTOMER LOCATION REPORT', head)

        # Report info
        row = 4
        sheet.write(row, 0, 'Report Date: ' + str(fields.Date.today()), txt_info)
        if data.get('date_from'):
            sheet.write(row + 1, 0, 'From Date: ' + str(data['date_from']), txt_info)
        if data.get('date_to'):
            sheet.write(row + 2, 0, 'To Date: ' + str(data['date_to']), txt_info)

        # Column headers
        row = 7
        headers = ['Unique ID', 'Customer Name', 'Location', 'Total Quantity', 'Total Value']
        for col_num, header_text in enumerate(headers):
            sheet.write(row, col_num, header_text, header)

        # Data rows
        row = 8
        grand_total_qty = 0
        grand_total_value = 0

        for record in query_result:
            sheet.write(row, 0, record.get('unique_id', ''), txt)
            sheet.write(row, 1, record.get('partner_name', ''), txt)
            sheet.write(row, 2, record.get('location_name', ''), txt)
            sheet.write(row, 3, record.get('total_qty', 0), number_format)
            sheet.write(row, 4, record.get('total_value', 0), number_format)

            grand_total_qty += record.get('total_qty', 0)
            grand_total_value += record.get('total_value', 0)
            row += 1

        # Grand totals
        row += 1
        sheet.write(row, 0, 'GRAND TOTAL', total_format)
        sheet.write(row, 1, '', total_format)
        sheet.write(row, 2, '', total_format)
        sheet.write(row, 3, grand_total_qty, total_format)
        sheet.write(row, 4, grand_total_value, total_format)

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
