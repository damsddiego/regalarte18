# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SngAiDashboardAnalysis(models.Model):
    _name = 'sng.ai.dashboard.analysis'
    _description = 'Análisis IA del Dashboard'
    _order = 'create_date desc'

    name = fields.Char(string="Referencia", compute='_compute_name', store=True)
    content = fields.Html(string="Análisis", sanitize=True)
    scope = fields.Selection(
        [
            ('general', 'General / Ventas'),
            ('customers', 'Clientes'),
            ('cxc', 'Cuentas por cobrar'),
            ('inventory', 'Inventario'),
        ],
        string="Pestaña",
        default='general',
        required=True,
        index=True,
    )
    provider_used = fields.Selection(
        [('anthropic', 'Anthropic'), ('deepseek', 'DeepSeek')],
        string="Proveedor IA",
    )
    model_used = fields.Char(string="Modelo IA")
    input_tokens = fields.Integer(string="Tokens de entrada")
    output_tokens = fields.Integer(string="Tokens de salida")
    cost_usd = fields.Float(string="Costo (USD)", digits=(12, 4))
    period_months = fields.Integer(string="Período (meses)", default=3)
    origin = fields.Selection(
        [('manual', 'Manual'), ('cron', 'Programado')],
        string="Origen", default='manual',
    )
    company_id = fields.Many2one(
        'res.company', string="Compañía",
        default=lambda self: self.env.company, required=True,
    )

    @api.depends('create_date', 'model_used')
    def _compute_name(self):
        for rec in self:
            dt = fields.Datetime.context_timestamp(
                rec, rec.create_date or fields.Datetime.now())
            rec.name = "Análisis %s" % dt.strftime('%d/%m/%Y %H:%M')
