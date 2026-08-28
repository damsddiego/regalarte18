from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user


class TestInvoiceReportSalespersonRules(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson_original = cls.env['res.partner'].create({
            'name': 'Original Salesperson',
            'is_salesperson': True,
        })
        cls.salesperson_report = cls.env['res.partner'].create({
            'name': 'Configured Report Salesperson',
            'is_salesperson': True,
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'Invoice Report Customer',
            'assigned_salesperson_id': cls.salesperson_original.id,
        })
        cls.invoice_user = new_test_user(
            cls.env,
            login='invoice-report-rule-user',
            groups='account.group_account_invoice',
            company_id=cls.env.company.id,
            name='Invoice Report Rule User',
        )
        cls.readonly_user = new_test_user(
            cls.env,
            login='invoice-report-readonly-user',
            groups='account.group_account_readonly',
            company_id=cls.env.company.id,
            name='Invoice Report Readonly User',
        )
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.customer.id,
            'invoice_date': '2026-05-10',
            'invoice_user_id': cls.invoice_user.id,
            'salesperson_id': cls.salesperson_original.id,
        })
        cls.rule = cls.env['invoice.report.salesperson.rule'].create({
            'company_id': cls.env.company.id,
            'user_id': cls.invoice_user.id,
            'salesperson_id': cls.salesperson_report.id,
        })

    def _create_wizard(self, **values):
        values.setdefault('date_from', '2026-05-01')
        values.setdefault('date_to', '2026-05-31')
        values.setdefault('company_ids', [(6, 0, self.env.company.ids)])
        return self.env['invoice.report.wizard'].create(values)

    def test_configured_rule_has_priority_without_modifying_invoice(self):
        wizard = self._create_wizard()

        self.assertEqual(
            wizard._get_effective_salesperson(self.invoice),
            self.salesperson_report,
        )
        self.assertEqual(self.invoice.salesperson_id, self.salesperson_original)

    def test_salesperson_filter_uses_configured_result(self):
        wizard_report = self._create_wizard(
            salesperson_ids=[(6, 0, self.salesperson_report.ids)]
        )
        wizard_original = self._create_wizard(
            salesperson_ids=[(6, 0, self.salesperson_original.ids)]
        )

        self.assertEqual(wizard_report._filter_report_moves(self.invoice), self.invoice)
        self.assertFalse(wizard_original._filter_report_moves(self.invoice))

    def test_inactive_rule_uses_current_fallback(self):
        self.rule.active = False

        self.assertEqual(
            self._create_wizard()._get_effective_salesperson(self.invoice),
            self.salesperson_original,
        )

    def test_rule_requires_salesperson_partner(self):
        invalid_partner = self.env['res.partner'].create({'name': 'Not Salesperson'})
        with self.assertRaises(ValidationError):
            self.rule.salesperson_id = invalid_partner

    def test_screen_lines_use_configured_salesperson(self):
        wizard = self._create_wizard(
            salesperson_ids=[(6, 0, self.salesperson_report.ids)]
        )
        self.invoice.state = 'posted'

        action = wizard.action_view_on_screen()

        self.assertEqual(action['res_model'], 'invoice.report.line')
        self.assertEqual(action['domain'], [('wizard_id', '=', wizard.id)])
        self.assertEqual(wizard.line_ids.move_id, self.invoice)
        self.assertEqual(wizard.line_ids.original_salesperson_id, self.salesperson_original)
        self.assertEqual(wizard.line_ids.salesperson_id, self.salesperson_report)

    def test_export_data_uses_configured_salesperson(self):
        wizard = self._create_wizard(
            salesperson_ids=[(6, 0, self.salesperson_report.ids)]
        )
        self.invoice.state = 'posted'

        data = wizard._get_report_data()

        self.assertEqual(data['invoice_count'], 1)
        self.assertEqual(
            data['data_by_salesperson'][0]['salesperson_id'],
            self.salesperson_report.id,
        )
        self.assertEqual(
            data['data_by_salesperson'][0]['invoices'][0]['number'],
            self.invoice.name,
        )

    def test_rule_is_scoped_by_company(self):
        other_company = self.env['res.company'].create({'name': 'Other Rule Company'})
        other_company_move = self.env['account.move'].new({
            'company_id': other_company.id,
            'invoice_user_id': self.invoice_user.id,
            'salesperson_id': self.salesperson_original.id,
        })

        self.assertEqual(
            self._create_wizard()._get_effective_salesperson(other_company_move),
            self.salesperson_original,
        )

    def test_rule_record_rule_restricts_companies(self):
        other_company = self.env['res.company'].create({'name': 'Hidden Rule Company'})
        hidden_rule = self.env['invoice.report.salesperson.rule'].sudo().create({
            'company_id': other_company.id,
            'user_id': self.invoice_user.id,
            'salesperson_id': self.salesperson_report.id,
        })

        visible_rules = self.env['invoice.report.salesperson.rule'].with_user(
            self.invoice_user
        ).search([])

        self.assertIn(self.rule, visible_rules)
        self.assertNotIn(hidden_rule, visible_rules)

    def test_readonly_accounting_user_can_generate_report_but_not_manage_rules(self):
        readonly_env = self.env(user=self.readonly_user)
        self.invoice.state = 'posted'

        wizard = readonly_env['invoice.report.wizard'].create({
            'date_from': '2026-05-01',
            'date_to': '2026-05-31',
            'company_ids': [(6, 0, self.env.company.ids)],
        })
        action = wizard.action_view_on_screen()
        invoice_line = wizard.line_ids.filtered(
            lambda line: line.move_id == self.invoice
        )

        self.assertEqual(action['res_model'], 'invoice.report.line')
        self.assertEqual(invoice_line.move_id, self.invoice)
        self.assertEqual(invoice_line.salesperson_id, self.salesperson_report)
        self.assertIn(
            self.rule,
            readonly_env['invoice.report.salesperson.rule'].search([]),
        )
        with self.assertRaises(AccessError):
            readonly_env['invoice.report.salesperson.rule'].create({
                'company_id': self.env.company.id,
                'user_id': self.readonly_user.id,
                'salesperson_id': self.salesperson_report.id,
            })
