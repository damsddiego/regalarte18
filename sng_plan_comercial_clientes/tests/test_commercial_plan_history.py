# -*- coding: utf-8 -*-

import base64
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook

from odoo.exceptions import ValidationError

from .test_commercial_plan import CommercialPlanCommon


class TestCommercialPlanHistory(CommercialPlanCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.sng_plan_odoo_start_date = date(2026, 4, 1)
        cls.history_model = cls.env['sng.commercial.plan.history']

    def _create_history(self, date_from, date_to, amount, partner=None):
        return self.history_model.create({
            'date_from': date_from,
            'date_to': date_to,
            'amount': amount,
            'partner_id': (partner or self.partner).id,
        })

    def _build_xlsx(self, rows):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'Ventas 2025'
        worksheet.append(['REGALARTE DE LAS AMERICAS S.A.'])
        worksheet.append(['VENTAS 2025', None, 'Del dia 01/01/2025 al 31/12/2025'])
        worksheet.append(['codigo', 'Cliente ', 'Ventas Netas IVAI', 'Ventas Brutas A.I'])
        for row in rows:
            worksheet.append(row)
        output = BytesIO()
        workbook.save(output)
        return base64.b64encode(output.getvalue())

    def _run_import(self, rows, **values):
        wizard = self.env['sng.commercial.plan.history.import.wizard'].create({
            'file_data': self._build_xlsx(rows),
            'file_name': 'ventas_2025.xlsx',
            'date_from': '2025-01-01',
            'date_to': '2025-12-31',
            **values,
        })
        wizard.action_import()
        return wizard

    def test_history_replaces_invoices_before_odoo_start(self):
        # Saldo de CxC cargado con fecha anterior al arranque: no es venta del periodo.
        self._create_posted_invoice('2026-02-10', 999.0)
        self._create_posted_invoice('2026-04-15', 300.0)
        self._create_history('2026-01-01', '2026-03-31', 700.0)
        self._create_history('2025-01-01', '2025-12-31', 5000.0)

        plan = self._create_plan(base_year=2026, target_year=2027)
        sales = plan._get_sales_by_partner(date(2026, 1, 1), date(2026, 12, 31))

        self.assertEqual(sales[self.partner.id], 1000.0)

    def test_history_counts_only_when_period_is_inside_range(self):
        self._create_history('2025-01-01', '2025-12-31', 5000.0)
        plan = self._create_plan()

        self.assertEqual(
            plan._get_sales_by_partner(date(2025, 1, 1), date(2025, 12, 31)),
            {self.partner.id: 5000.0},
        )
        self.assertEqual(plan._get_sales_by_partner(date(2025, 7, 1), date(2025, 12, 31)), {})

    def test_history_cannot_reach_odoo_start_or_overlap(self):
        with self.assertRaises(ValidationError):
            self._create_history('2026-03-01', '2026-04-30', 100.0)

        self._create_history('2025-01-01', '2025-12-31', 100.0)
        with self.assertRaises(ValidationError):
            self._create_history('2025-03-01', '2025-03-31', 100.0, partner=self.other_partner)
        # El mismo periodo para otro cliente es valido.
        self._create_history('2025-01-01', '2025-12-31', 50.0, partner=self.other_partner)

    def test_history_gap_warning(self):
        self._create_history('2025-01-01', '2025-12-31', 100.0)
        plan = self._create_plan()

        self.assertIn('01/01/2026 al 31/03/2026', plan.history_warning)
        self.assertNotIn('2025', plan.history_warning)

        self._create_history('2026-01-01', '2026-01-31', 10.0)
        self._create_history('2026-02-01', '2026-03-31', 10.0)
        plan.invalidate_recordset(['history_warning'])
        self.assertFalse(plan.history_warning)

    def test_dpp_before_odoo_start_uses_payments_since_start(self):
        plan = self._create_plan()
        with patch.object(
            type(self.env['regalarte.customer.metric']),
            '_get_dpp_metrics',
            autospec=True,
            return_value={},
        ) as dpp_mock:
            plan._get_dpp_by_partner(
                partner_ids=[self.partner.id],
                date_from=date(2025, 1, 1),
                date_to=date(2025, 12, 31),
            )

        self.assertEqual(dpp_mock.call_args.kwargs['date_from'], date(2026, 4, 1))
        self.assertIsNone(dpp_mock.call_args.kwargs['date_to'])

    def test_import_matches_by_code_name_and_previous_assignment(self):
        if 'unique_id' not in self.env['res.partner']._fields:
            self.skipTest('customer_sequence no esta instalado.')
        self.partner.unique_id = '90001'
        vendor = self.env['res.partner'].create({
            'name': 'Proveedor Mismo Codigo',
            'unique_id': '90002',
            'supplier_rank': 1,
        })
        self.other_partner.unique_id = '90002'
        unknown_partner = self.env['res.partner'].create({
            'name': 'Cliente Sin Codigo Plan',
            'customer_rank': 1,
        })

        wizard = self._run_import([
            [90001, 'Cliente Plan A', 1000.0, 885.0],
            [90002, 'Cliente Plan B', 500.0, 442.0],
            [90003, 'CLIENTE SIN CODIGO PLAN', 200.0, 177.0],
            [90004, 'Cliente Inexistente', 50.0, 44.0],
            [None, 'Total', 1750.0, 1548.0],
        ])

        rows = self.history_model.search([('source_file', '=', 'ventas_2025.xlsx')])
        by_code = {row.source_code: row for row in rows}
        self.assertEqual(len(rows), 4)
        self.assertEqual(by_code['90001'].partner_id, self.partner)
        self.assertEqual(by_code['90002'].partner_id, self.other_partner)
        self.assertNotEqual(by_code['90002'].partner_id, vendor)
        self.assertEqual(by_code['90003'].partner_id, unknown_partner)
        self.assertEqual(by_code['90003'].match_method, 'name')
        self.assertFalse(by_code['90004'].partner_id)
        self.assertIn('Sin asignar: 1', wizard.result_message)

        by_code['90004'].partner_id = unknown_partner
        self.assertEqual(by_code['90004'].match_method, 'manual')

        # Reimportar el mismo periodo reemplaza las filas y conserva la asignacion manual.
        self._run_import([
            [90001, 'Cliente Plan A', 1100.0, 970.0],
            [90004, 'Cliente Inexistente', 60.0, 53.0],
        ])
        rows = self.history_model.search([('date_from', '=', '2025-01-01')])
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(rows.mapped('amount')), 1160.0)
        reassigned = rows.filtered(lambda row: row.source_code == '90004')
        self.assertEqual(reassigned.partner_id, unknown_partner)
        self.assertEqual(reassigned.match_method, 'history')

    def test_load_customers_from_history(self):
        self._create_history('2025-01-01', '2025-12-31', 800.0)
        self._create_history('2025-01-01', '2025-12-31', 200.0, partner=self.other_partner)
        plan = self._create_plan()

        plan.action_load_customers()

        self.assertEqual(plan.line_ids.partner_id, self.partner | self.other_partner)
