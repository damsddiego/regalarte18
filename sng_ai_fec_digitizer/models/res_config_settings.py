# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sng_ai_fec_confidence_threshold = fields.Float(
        string="Confianza mínima FEC IA",
        config_parameter="sng_ai_fec_digitizer.confidence_threshold",
        default=0.80,
    )
    sng_ai_fec_max_pages = fields.Integer(
        string="Máximo de páginas por lote FEC",
        config_parameter="sng_ai_fec_digitizer.max_pages",
        default=30,
    )
    sng_ai_fec_max_file_mb = fields.Integer(
        string="Tamaño máximo del PDF (MB)",
        config_parameter="sng_ai_fec_digitizer.max_file_mb",
        default=20,
    )
    sng_ai_fec_max_cost_usd = fields.Float(
        string="Costo máximo estimado por lote (USD)",
        config_parameter="sng_ai_fec_digitizer.max_cost_usd",
        default=5.0,
    )
    sng_ai_fec_journal_id = fields.Many2one(
        "account.journal",
        string="Diario predeterminado para FEC",
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        config_parameter="sng_ai_fec_digitizer.journal_id",
    )

