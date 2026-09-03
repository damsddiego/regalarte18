# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

JOURNAL_CODE = "FSFE"
JOURNAL_NAME = "Facturas de Proveedor (Sin FE)"


def post_init_hook(env):
    """Crea el diario dedicado por compañía copiando la configuración contable
    del diario de compras principal (FACTU) si aún no existe."""
    Journal = env["account.journal"]
    for company in env["res.company"].search([]):
        existing = Journal.with_context(active_test=False).search(
            [("code", "=", JOURNAL_CODE), ("company_id", "=", company.id)], limit=1
        )
        if existing:
            existing.fe_disabled_journal = True
            continue
        base = Journal.search(
            [("code", "=", "FACTU"), ("company_id", "=", company.id)], limit=1
        ) or Journal.search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1
        )
        if not base:
            _logger.warning("No hay diario de compras base en %s; no se crea %s", company.name, JOURNAL_CODE)
            continue
        vals = {
            "name": JOURNAL_NAME,
            "code": JOURNAL_CODE,
            "type": "purchase",
            "company_id": company.id,
            "default_account_id": base.default_account_id.id,
            "currency_id": base.currency_id.id,
            "refund_sequence": base.refund_sequence,
            "invoice_reference_type": base.invoice_reference_type,
            "invoice_reference_model": base.invoice_reference_model,
            "fe_disabled_journal": True,
            "sequence": base.sequence + 1,
        }
        for f in ("sucursal", "terminal", "expense_product_id", "expense_account_id", "expense_analytic_account_id"):
            if f in Journal._fields:
                v = base[f]
                vals[f] = v.id if hasattr(v, "id") else v
        j = Journal.create(vals)
        _logger.info("Diario %s (id %s) creado en %s a partir de %s", JOURNAL_CODE, j.id, company.name, base.code)
