# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    clase_abc = fields.Selection(
        [("a", "A"), ("b", "B"), ("c", "C")],
        string="Clase ABC",
        readonly=True,
        index=True,
        copy=False,
        help=(
            "Clasificación ABC por venta valorizada de los últimos 6 meses "
            "(unidades netas facturadas × precio actual), misma regla del "
            "reporte Análisis de Compras: A acumula hasta el 80% del valor "
            "vendido, B hasta el 95%, C el resto. La recalcula un cron diario."
        ),
    )
    clase_abc_date = fields.Datetime(
        string="Clase ABC calculada el",
        readonly=True,
        copy=False,
    )

    def cron_compute_clase_abc(self):
        """Recalcula la clase ABC de todos los productos comprables/almacenables.

        Reutiliza la consulta de ventas, el precio y la asignación ABC del
        wizard de Análisis de Compras para que ambos den la misma clase con
        parámetros por defecto (todas las compañías, todos los almacenes,
        últimos 6 meses calendario).
        """
        wizard = self.env["sng.analisis.compras.wizard"].sudo().create({
            "company_ids": [(6, 0, self.env["res.company"].sudo().search([]).ids)],
        })
        products = self.sudo().search(wizard._get_product_domain())
        if not products:
            return True

        self.env.flush_all()
        months = wizard._get_month_starts()
        sales_rows = wizard._execute_sales_query(
            products.ids, months[0], months[-1] + relativedelta(months=1)
        )
        qty_map = dict(sales_rows)
        price_map = wizard._get_price_map(products)

        rows = [
            {
                "product_id": product.id,
                "venta_valorizada": qty_map.get(product.id, 0.0)
                * price_map[product.id]["precio"],
                "clase_abc": "c",
            }
            for product in products
        ]
        wizard._assign_abc(rows)

        now = fields.Datetime.now()
        by_class = {"a": [], "b": [], "c": []}
        for row in rows:
            by_class[row["clase_abc"]].append(row["product_id"])
        for abc_class, ids in by_class.items():
            if ids:
                self.sudo().browse(ids).write({
                    "clase_abc": abc_class,
                    "clase_abc_date": now,
                })
        # Productos fuera del dominio (ya no comprables/almacenables) pierden la clase.
        stale = self.sudo().search([
            ("clase_abc", "!=", False),
            ("id", "not in", products.ids),
        ])
        if stale:
            stale.write({"clase_abc": False, "clase_abc_date": now})

        _logger.info(
            "Clase ABC recalculada: %s A, %s B, %s C (%s productos)",
            len(by_class["a"]), len(by_class["b"]), len(by_class["c"]), len(products),
        )
        return True
