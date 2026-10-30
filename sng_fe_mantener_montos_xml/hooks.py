# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Marca las líneas de los borradores ya importados desde XML antes de instalar el módulo."""
    moves = env["account.move"].search(
        [
            ("move_type", "in", ("in_invoice", "in_refund")),
            ("state", "=", "draft"),
            ("xml_supplier_approval", "!=", False),
        ]
    )
    moves._sng_mark_xml_lines()
    _logger.info(
        "sng_fe_mantener_montos_xml: %d borradores con XML revisados, %d líneas marcadas",
        len(moves),
        len(moves.invoice_line_ids.filtered("fe_xml_line")),
    )
