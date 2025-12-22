from odoo import models, fields
from odoo.exceptions import UserError
import base64
from io import BytesIO
import xlsxwriter


class StockLandedCostExportWizard(models.TransientModel):
    _name = 'stock.landed.cost.export.wizard'
    _description = 'Exportar costos en Excel'

    date_from = fields.Date('Fecha Desde', required=True)
    date_end = fields.Date('Fecha Hasta', required=True)

    file_data = fields.Binary('Archivo', readonly=True)
    file_name = fields.Char('Nombre del Archivo', readonly=True)

    def action_export_excel(self):
        if self.date_from > self.date_end:
            raise UserError("La fecha 'Desde' no puede ser mayor que la fecha 'Hasta'.")

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Costos')

        # FORMATO
        bold = workbook.add_format({'bold': True})
        center_bold = workbook.add_format({'bold': True, 'align': 'center'})
        moneda = workbook.add_format({'num_format': '$#,##0.00', 'align': 'right'})
        normal = workbook.add_format({'align': 'left'})

        company_name = self.env.company.name
        sheet.merge_range('A1:E1', f'Reporte de Costos por Importación - {company_name}', center_bold)
        sheet.merge_range('A2:E2',
                          f"Desde: {self.date_from.strftime('%Y-%m-%d')}  Hasta: {self.date_end.strftime('%Y-%m-%d')}",
                          normal)

        headers = ['Fecha', 'Proveedor(es)', 'Factura(s)', 'FOB', 'Costo Total']
        for col, header in enumerate(headers):
            sheet.write(3, col, header, bold)

        records = self.env['stock.landed.cost'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_end),
            ('state', '=', 'done'),
        ])

        total_fob = 0.0
        total_cost = 0.0
        for row, rec in enumerate(records, start=4):  # fila 4 después de título y encabezado
            fob = sum(po.amount_total for po in rec.purchase_ids)
            total_fob += fob
            total_cost += rec.amount_total

            proveedores = ", ".join(str(name) for name in rec.purchase_ids.mapped('partner_id.name') if name)
            facturas = ", ".join(str(f or '') for f in rec.purchase_ids.mapped('partner_ref'))

            sheet.write(row, 0, str(rec.date) if rec.date else '', normal)
            sheet.write(row, 1, proveedores, normal)
            sheet.write(row, 2, facturas or rec.ref or '', normal)
            sheet.write(row, 3, fob, moneda)
            sheet.write(row, 4, rec.amount_total, moneda)

        # Totales en la última fila
        total_row = len(records) + 4
        total_bold = workbook.add_format({'bold': True, 'num_format': '$#,##0.00', 'align': 'right'})
        label_bold = workbook.add_format({'bold': True, 'align': 'right'})

        sheet.write(total_row, 2, 'TOTAL GENERAL:', label_bold)
        sheet.write(total_row, 3, total_fob, total_bold)
        sheet.write(total_row, 4, total_cost, total_bold)

        sheet.set_column('A:A', 12)  # Fecha
        sheet.set_column('B:B', 25)  # Proveedores
        sheet.set_column('C:C', 25)  # Facturas
        sheet.set_column('D:E', 15)  # Montos

        workbook.close()
        output.seek(0)
        xlsx_data = output.read()
        output.close()

        self.write({
            'file_data': base64.b64encode(xlsx_data),
            'file_name': f"Importaciones_{self.date_from.strftime('%Y-%m-%d')}_al_{self.date_end.strftime('%Y-%m-%d')}.xlsx",
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.landed.cost.export.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
