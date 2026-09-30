# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    _sql_constraints = [
        (
            "default_code_uniq",
            "unique(default_code)",
            "La referencia interna debe ser única. Ya existe otro producto con la misma referencia.",
        ),
    ]

    @api.constrains("default_code")
    def _check_unique_default_code(self):
        """Give users a clear error before the database constraint is reached."""
        for product in self:
            if not product.default_code:
                continue

            duplicate = self.sudo().with_context(active_test=False).search(
                [
                    ("default_code", "=", product.default_code),
                    ("id", "!=", product.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "La referencia interna '%(code)s' ya está asignada al producto "
                        "'%(product)s'.",
                        code=product.default_code,
                        product=duplicate.display_name,
                    )
                )
