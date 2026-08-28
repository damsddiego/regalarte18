# -*- coding: utf-8 -*-
import random
from datetime import date, datetime

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CycleCountConfig(models.Model):
    _name = "sng.cycle.count.config"
    _description = "Configuración de Conteo Cíclico"
    _order = "priority, id"

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Compañía", default=lambda self: self.env.company, required=True
    )

    # Ubicaciones y categorías
    location_ids = fields.Many2many(
        "stock.location", string="Ubicaciones",
        domain="[('usage', 'in', ['internal', 'transit']), ('company_id', 'in', [company_id, False])]"
    )
    categ_ids = fields.Many2many(
        "product.category", string="Categorías de Producto"
    )

    # Criterios de selección
    selection_method = fields.Selection([
        ("rotation", "Rotación (movimientos recientes)"),
        ("value", "Valor de inventario"),
        ("category", "Categoría específica"),
        ("abc", "Clasificación ABC"),
        ("random", "Aleatorio"),
    ], string="Método de Selección", required=True, default="rotation")

    abc_classification = fields.Selection([
        ("all", "Todas"),
        ("a", "A"),
        ("b", "B"),
        ("c", "C"),
    ], string="Clasificación ABC", default="all",
        help=(
            "Filtra por la Clase ABC del producto, calculada a diario por el "
            "cron de Análisis de Compras (venta valorizada de los últimos 6 "
            "meses: A acumula el 80% del valor vendido, B hasta el 95%, C el "
            "resto). 'Todas' no filtra y ordena por valor de inventario."
        ))

    rotation_days = fields.Integer(string="Días de Rotación", default=30,
                                   help="Cantidad de días hacia atrás para evaluar movimientos de stock.")
    min_stock_value = fields.Float(string="Valor Mínimo de Stock", default=0.0,
                                   help="Solo incluir productos cuyo valor a mano sea mayor o igual a este monto.")
    daily_product_count = fields.Integer(string="Productos por Día", default=10, required=True,
                                         help="Cantidad máxima de productos a seleccionar diariamente con esta regla.")
    priority = fields.Integer(string="Prioridad", default=10,
                              help="Orden de ejecución. Menor número = mayor prioridad.")
    user_id = fields.Many2one(
        "res.users", string="Operador Asignado",
        help="Usuario que recibirá los conteos generados. Si se deja vacío, se asignará según rotación o al usuario actual."
    )
    min_days_between_counts = fields.Integer(
        string="Días Mínimos entre Conteos", default=7,
        help="Evita seleccionar el mismo producto si ya fue contado en los últimos N días."
    )
    include_negative = fields.Boolean(
        string="Incluir Stock Negativo", default=True,
        help=(
            "Incluye quants con cantidad negativa (permitidos por stock "
            "negativo). Un negativo casi siempre indica un descuadre, por lo "
            "que son buenos candidatos a conteo. En los métodos por valor y "
            "ABC compiten por su valor absoluto."
        ),
    )

    @api.constrains("rotation_days")
    def _check_rotation_days(self):
        for config in self:
            if config.selection_method == "rotation" and config.rotation_days <= 0:
                raise ValidationError(_("Los días de rotación deben ser mayores a 0."))

    @api.constrains("daily_product_count")
    def _check_daily_product_count(self):
        for config in self:
            if config.daily_product_count <= 0:
                raise ValidationError(_("La cantidad de productos por día debe ser mayor a 0."))

    def _get_base_domain(self):
        self.ensure_one()
        domain = [
            ("location_id.usage", "in", ["internal", "transit"]),
            ("quantity", "!=", 0) if self.include_negative else ("quantity", ">", 0),
        ]
        if self.location_ids:
            domain.append(("location_id", "in", self.location_ids.ids))
        if self.categ_ids:
            domain.append(("product_id.categ_id", "in", self.categ_ids.ids))
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))
        return domain

    def _get_rotation_order(self):
        """Retorna un dominio/orden para productos por rotación."""
        self.ensure_one()
        date_from = fields.Datetime.subtract(fields.Datetime.now(), days=self.rotation_days)
        # Leer movimientos hechos en el rango para calcular rotación
        move_lines = self.env["stock.move.line"].sudo().read_group(
            [
                ("state", "=", "done"),
                ("date", ">=", date_from),
                ("location_id.usage", "in", ["internal", "transit"]),
            ],
            ["product_id", "quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        product_rotation = {m["product_id"][0]: m["quantity"] for m in move_lines if m.get("product_id")}
        return product_rotation

    def _select_quants(self):
        """Selecciona los stock.quant según la configuración."""
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()
        domain = self._get_base_domain()

        candidates = Quant.search(domain)

        # Un quant que ya pertenece a un conteo abierto no debe volver a
        # programarse, aunque el nuevo conteo provenga de otra configuracion.
        # Esperar a que la linea quede ``adjusted`` provoca que los borradores
        # pendientes se repitan todos los dias.
        open_lines = self.env["sng.cycle.count.line"].sudo().search([
            ("quant_id", "in", candidates.ids),
            (
                "cycle_count_id.state",
                "in",
                ["draft", "in_progress", "pending_approval"],
            ),
        ])
        excluded_quant_ids = set(open_lines.mapped("quant_id.id"))

        # Excluir tambien quants aprobados y contados recientemente.
        if self.min_days_between_counts > 0:
            cutoff_date = fields.Datetime.subtract(fields.Datetime.now(), days=self.min_days_between_counts)
            recent_lines = self.env["sng.cycle.count.line"].sudo().search([
                ("quant_id", "in", candidates.ids),
                ("state", "=", "adjusted"),
                ("count_date", ">=", cutoff_date),
            ])
            excluded_quant_ids.update(recent_lines.mapped("quant_id.id"))

        if excluded_quant_ids:
            candidates = candidates.filtered(lambda q: q.id not in excluded_quant_ids)

        # Filtrar por valor mínimo (valor absoluto: un negativo grande también importa)
        if self.min_stock_value > 0:
            candidates = candidates.filtered(
                lambda q: abs(q.quantity * q.product_id.standard_price) >= self.min_stock_value
            )

        # Ordenar según método
        if self.selection_method == "rotation":
            rotation_map = self._get_rotation_order()
            candidates = candidates.sorted(
                lambda q: rotation_map.get(q.product_id.id, 0.0),
                reverse=True,
            )
        elif self.selection_method == "value":
            candidates = candidates.sorted(
                lambda q: abs(q.quantity * q.product_id.standard_price),
                reverse=True,
            )
        elif self.selection_method == "random":
            candidates_list = list(candidates)
            random.shuffle(candidates_list)
            candidates = self.env["stock.quant"].browse([q.id for q in candidates_list])
        elif self.selection_method == "abc":
            # Clase ABC persistente (product.clase_abc, calculada por el cron
            # diario de sng_analisis_compras: venta valorizada 6m, A ≤80%, B ≤95%).
            if self.abc_classification and self.abc_classification != "all":
                candidates = candidates.filtered(
                    lambda q: q.product_id.clase_abc == self.abc_classification
                )
            candidates = candidates.sorted(
                lambda q: abs(q.quantity * q.product_id.standard_price),
                reverse=True,
            )
        else:
            candidates = candidates.sorted(lambda q: q.product_id.default_code or q.product_id.name)

        # Tomar los primeros N
        selected = candidates[: self.daily_product_count]
        return selected

    def cron_generate_daily_counts(self):
        """Método llamado por el cron para generar conteos diarios."""
        configs = self.search([("active", "=", True)])
        for config in configs:
            quants = config._select_quants()
            if not quants:
                continue

            # Si la config no define operador, dejamos user_id en False (no OdooBot/cron)
            # para que las record rules permitan a cualquier operador ver el conteo.
            count_vals = {
                "config_id": config.id,
                "count_date": date.today(),
                "user_id": config.user_id.id if config.user_id else False,
                "state": "draft",
                "company_id": config.company_id.id,
            }
            cycle_count = self.env["sng.cycle.count"].create(count_vals)
            line_vals = []
            for quant in quants:
                line_vals.append((0, 0, {
                    "quant_id": quant.id,
                    "theoretical_qty": quant.quantity,
                }))
            cycle_count.write({"line_ids": line_vals})
        return True
