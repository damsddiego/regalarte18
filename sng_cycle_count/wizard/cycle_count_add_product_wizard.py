# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CycleCountAddProductWizard(models.TransientModel):
    _name = "sng.cycle.count.add.product.wizard"
    _description = "Agregar producto a Conteo Cíclico"

    cycle_count_id = fields.Many2one(
        "sng.cycle.count", string="Conteo", required=True, readonly=True
    )
    company_id = fields.Many2one(related="cycle_count_id.company_id")
    product_id = fields.Many2one(
        "product.product",
        string="Producto",
        required=True,
        domain="[('type', '=', 'consu'), ('is_storable', '=', True)]",
    )
    tracking = fields.Selection(related="product_id.tracking")
    location_id = fields.Many2one(
        "stock.location",
        string="Ubicación",
        required=True,
        domain="[('usage', 'in', ('internal', 'transit')), ('company_id', 'in', (False, company_id))]",
    )
    allowed_location_ids = fields.Many2many(
        "stock.location", compute="_compute_allowed_location_ids"
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lote / Serie",
        domain="[('product_id', '=', product_id)]",
    )
    counted_qty = fields.Float(
        string="Cantidad Contada", digits="Product Unit of Measure", default=0.0
    )
    notes = fields.Text(string="Observaciones")

    @api.depends("cycle_count_id")
    def _compute_allowed_location_ids(self):
        for wizard in self:
            count = wizard.cycle_count_id
            locations = count.line_ids.mapped("location_id")
            if not locations and count.config_id:
                locations = count.config_id.location_ids
            wizard.allowed_location_ids = locations

    @api.onchange("cycle_count_id")
    def _onchange_cycle_count_id(self):
        if self.allowed_location_ids and len(self.allowed_location_ids) == 1:
            self.location_id = self.allowed_location_ids

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.lot_id = False

    def _find_or_create_quant(self):
        self.ensure_one()
        Quant = self.env["stock.quant"].sudo()
        domain = [
            ("product_id", "=", self.product_id.id),
            ("location_id", "=", self.location_id.id),
            ("lot_id", "=", self.lot_id.id or False),
            ("package_id", "=", False),
            ("owner_id", "=", False),
        ]
        quant = Quant.search(domain, order="id", limit=1)
        if quant:
            return quant
        # Producto sin existencias en la ubicación: se crea el quant en cero
        # para poder registrar el sobrante en el conteo.
        return Quant.with_context(inventory_mode=True).create(
            {
                "product_id": self.product_id.id,
                "location_id": self.location_id.id,
                "lot_id": self.lot_id.id or False,
                "company_id": self.cycle_count_id.company_id.id,
            }
        )

    def action_confirm(self):
        self.ensure_one()
        count = self.cycle_count_id
        if count.state not in ("draft", "in_progress"):
            raise UserError(_("Solo puede agregar productos a un conteo en borrador o en progreso."))
        if self.allowed_location_ids and self.location_id not in self.allowed_location_ids:
            raise UserError(
                _("La ubicación %s no pertenece a este conteo.") % self.location_id.display_name
            )
        if self.product_id.tracking != "none" and not self.lot_id:
            raise UserError(_("El producto requiere lote o número de serie."))
        if self.counted_qty < 0:
            raise UserError(_("La cantidad contada no puede ser negativa."))

        quant = self._find_or_create_quant()
        Line = self.env["sng.cycle.count.line"]
        if Line.sudo().search_count(
            [("cycle_count_id", "=", count.id), ("quant_id", "=", quant.id)], limit=1
        ):
            raise UserError(_("Este producto ya está incluido en el conteo."))
        other = Line.sudo().search(
            [
                ("quant_id", "=", quant.id),
                ("cycle_count_id", "!=", count.id),
                ("cycle_count_id.state", "in", ("draft", "in_progress", "pending_approval")),
            ],
            limit=1,
        )
        if other:
            raise UserError(
                _("Este producto ya está en el conteo abierto %s.") % other.cycle_count_id.name
            )

        line = Line.create(
            {
                "cycle_count_id": count.id,
                "quant_id": quant.id,
                "theoretical_qty": quant.quantity,
                "counted_qty": self.counted_qty,
                "state": "counted",
                "count_date": fields.Datetime.now(),
                "is_manual": True,
                "notes": self.notes,
            }
        )
        count.message_post(
            body=_(
                "%(user)s agregó manualmente %(product)s en %(location)s "
                "(teórico %(theo)s, contado %(counted)s)."
            )
            % {
                "user": self.env.user.display_name,
                "product": line.product_id.display_name,
                "location": line.location_id.display_name,
                "theo": line.theoretical_qty,
                "counted": line.counted_qty,
            },
            subtype_xmlid="mail.mt_note",
        )
        return {"type": "ir.actions.act_window_close"}
