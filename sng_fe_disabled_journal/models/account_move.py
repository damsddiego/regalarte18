# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _electronic_documents_disabled(self):
        self.ensure_one()
        if self.journal_id.fe_disabled_journal:
            return True
        return super()._electronic_documents_disabled()

    def _next_disabled_document_sequence(self):
        """En un diario sin FE no se consume la secuencia DA: devolver False hace que
        cr_electronic_invoice conserve el nombre asignado por la numeración estándar
        del diario, evitando dos contadores sobre el mismo patrón de nombres."""
        self.ensure_one()
        if self.journal_id.fe_disabled_journal:
            return False
        return super()._next_disabled_document_sequence()

    @api.onchange("journal_id")
    def _onchange_journal_fe_disabled(self):
        if self.journal_id.fe_disabled_journal and self.move_type in ("in_invoice", "in_refund"):
            self.tipo_documento = "disabled"
