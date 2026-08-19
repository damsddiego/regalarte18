# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SngFakeReconcileConfig(models.Model):
    _name = "sng.fake.reconcile.config"
    _description = "Configuración de Conciliación Falsa Bancaria"
    _check_company_auto = True

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario Bancario",
        required=True,
        check_company=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
    )
    date_tolerance_days = fields.Integer(
        string="Tolerancia de Días",
        default=2,
        required=True,
        help="Días de tolerancia alrededor de la fecha de la línea del extracto.",
    )
    amount_tolerance_pct = fields.Float(
        string="Tolerancia de Monto (%)",
        default=0.0,
        required=True,
        help="Porcentaje de tolerancia de monto. 0.0 = monto exacto; 0.05 = 5%.",
    )
    min_score_to_suggest = fields.Float(
        string="Score Mínimo para Sugerir",
        default=70.0,
        required=True,
        help="Score mínimo (0-100) para proponer un pago candidato automáticamente.",
    )
    min_score_gap = fields.Float(
        string="Diferencia Mínima con el Segundo",
        default=10.0,
        required=True,
        help="Diferencia mínima de score entre el primer y segundo candidato para aceptar la sugerencia.",
    )
    enable_amount_date_match = fields.Boolean(
        string="Usar Monto y Fecha",
        default=True,
    )
    enable_partner_match = fields.Boolean(
        string="Usar Cliente",
        default=True,
    )
    enable_reference_match = fields.Boolean(
        string="Usar Referencia/Factura",
        default=True,
    )
    reference_regex = fields.Char(
        string="Regex de Referencia",
        default=r"(?:FAC|FACT|INV|FA|F)[\s\-]?#?(\d+)",
        help="Expresión regular para extraer número de factura/referencia del texto del depósito.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "unique_journal_config",
            "UNIQUE(journal_id)",
            "Solo puede existir una configuración por diario bancario.",
        ),
    ]

    @api.depends("journal_id")
    def _compute_name(self):
        for config in self:
            config.name = config.journal_id.display_name or "Configuración"

    @api.constrains("date_tolerance_days")
    def _check_date_tolerance_days(self):
        for config in self:
            if config.date_tolerance_days < 0:
                raise ValidationError(_("La tolerancia de días no puede ser negativa."))

    @api.constrains("amount_tolerance_pct")
    def _check_amount_tolerance_pct(self):
        for config in self:
            if config.amount_tolerance_pct < 0 or config.amount_tolerance_pct > 1:
                raise ValidationError(_("La tolerancia de monto debe estar entre 0.0 y 1.0 (0%% - 100%%)."))

    @api.constrains("min_score_to_suggest", "min_score_gap")
    def _check_scores(self):
        for config in self:
            if not (0 <= config.min_score_to_suggest <= 100):
                raise ValidationError(_("El score mínimo debe estar entre 0 y 100."))
            if not (0 <= config.min_score_gap <= 100):
                raise ValidationError(_("La diferencia mínima debe estar entre 0 y 100."))

    @api.model
    def get_config_for_journal(self, journal):
        """Obtiene la configuración activa para un diario, o la default."""
        if not journal:
            return self.browse(False)
        return self.search(
            [
                ("journal_id", "=", journal.id),
                ("company_id", "=", journal.company_id.id),
                ("active", "=", True),
            ],
            limit=1,
        )
