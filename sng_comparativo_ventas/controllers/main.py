# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import content_disposition, request
from odoo.http import serialize_exception as _serialize_exception
from odoo.tools import html_escape


class ComparativoXlsxController(http.Controller):

    @http.route(
        "/comparativo_ventas/xlsx",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def download_xlsx(self, model, options, output_format, report_name, **kw):
        options = json.loads(options)
        try:
            report_obj = request.env[model].with_user(request.session.uid)
            response = request.make_response(
                None,
                headers=[
                    ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    ("Content-Disposition", content_disposition(report_name + ".xlsx")),
                ],
            )
            report_obj.get_xlsx_report(options, response)
            return response
        except Exception as e:
            se = _serialize_exception(e)
            error = {"code": 200, "message": "Odoo Server Error", "data": se}
            return request.make_response(html_escape(json.dumps(error)))
