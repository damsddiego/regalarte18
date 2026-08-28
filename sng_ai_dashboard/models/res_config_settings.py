# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sng_ai_provider = fields.Selection(
        [
            ('anthropic', 'Anthropic (Claude)'),
            ('deepseek', 'DeepSeek'),
        ],
        string="Proveedor de IA",
        config_parameter='sng_ai_dashboard.provider',
        default='deepseek',
        required=True,
    )
    sng_ai_api_key = fields.Char(
        string="API Key de Anthropic",
        config_parameter='sng_ai_dashboard.api_key',
        help="Clave de la API de Anthropic (platform.claude.com). "
             "Se usa para generar los análisis del Dashboard IA.",
    )
    sng_ai_inventory_warehouses = fields.Char(
        string="Almacenes de inventario",
        config_parameter='sng_ai_dashboard.inventory_warehouse_codes',
        default='WH',
        help="Códigos de almacén (separados por coma) para la pestaña de "
             "inventario del Dashboard IA. Ej: WH,BBAOD",
    )
    sng_ai_model = fields.Selection(
        [
            ('claude-opus-4-8', 'Claude Opus 4.8 (mejor análisis)'),
            ('claude-sonnet-5', 'Claude Sonnet 5 (equilibrado)'),
            ('claude-haiku-4-5', 'Claude Haiku 4.5 (más económico)'),
        ],
        string="Modelo IA",
        config_parameter='sng_ai_dashboard.model',
        default='claude-opus-4-8',
    )
    sng_ai_deepseek_api_key = fields.Char(
        string="API Key de DeepSeek",
        config_parameter='sng_ai_dashboard.deepseek_api_key',
        help="Clave generada en platform.deepseek.com.",
    )
    sng_ai_deepseek_model = fields.Selection(
        [
            ('deepseek-v4-flash', 'DeepSeek V4 Flash (más económico)'),
            ('deepseek-v4-pro', 'DeepSeek V4 Pro (mejor análisis)'),
        ],
        string="Modelo DeepSeek",
        config_parameter='sng_ai_dashboard.deepseek_model',
        default='deepseek-v4-flash',
    )
    sng_ai_deepseek_base_url = fields.Char(
        string="URL base de DeepSeek",
        config_parameter='sng_ai_dashboard.deepseek_base_url',
        default='https://api.deepseek.com',
        help="Permite cambiar el endpoint sin modificar el módulo.",
    )
