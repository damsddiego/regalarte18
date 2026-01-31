import json
from odoo import http
from odoo.http import content_disposition, request
from odoo.tools import html_escape


class XLSXReportController(http.Controller):

    @http.route('/report/download', type='http', auth="user")
    def report_download(self, data, context=None, **kw):
        """Download XLSX report."""
        requestcontent = json.loads(data)
        url, report_type = requestcontent[0], requestcontent[1]

        if report_type == 'xlsx':
            try:
                reportname = url.split('/report/xlsx/')[1].split('?')[0]

                # Parse options from URL
                docids = None
                options = {}
                if '?' in url:
                    try:
                        # Extract the options parameter
                        query_string = url.split('?')[1]
                        params = query_string.split('&')
                        for param in params:
                            if '=' in param:
                                key, value = param.split('=', 1)
                                if key == 'options' and value:
                                    options = json.loads(value)
                                    break
                    except (IndexError, json.JSONDecodeError, ValueError):
                        # If parsing fails, use empty options
                        options = {}

                # Get the report model
                if reportname == 'sng.stock.customer.report':
                    wizard = request.env['sng.stock.customer.report'].sudo()
                    response = request.make_response(
                        None,
                        headers=[
                            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                            ('Content-Disposition', content_disposition('Stock_By_Customer_Location_Report.xlsx'))
                        ]
                    )
                    wizard.get_xlsx_report(options, response)
                    return response

            except Exception as e:
                se = http.serialize_exception(e)
                error = {
                    'code': 200,
                    'message': 'Odoo Server Error',
                    'data': se
                }
                return request.make_response(html_escape(json.dumps(error)))
        else:
            return
