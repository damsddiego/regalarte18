# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    origen = fields.Char(
        string="Origen",
        help="Origen del traslado (ej. App).",
    )
    auto_confirm_pending = fields.Boolean(
        string="Auto confirmar pendiente",
        default=False,
        help="Marca interna para confirmar automaticamente cuando existan lineas.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get("skip_auto_confirm"):
            return records

        to_flag = records.filtered(lambda p: p.origen == "App")
        if to_flag:
            to_flag.with_context(skip_auto_confirm=True).write(
                {"auto_confirm_pending": True}
            )
            to_process = to_flag.filtered(lambda p: p.move_ids)
            if to_process:
                to_process.with_context(skip_auto_confirm=True)._auto_confirm_and_validate()
                to_process.with_context(skip_auto_confirm=True).write(
                    {"auto_confirm_pending": False}
                )
        return records

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("skip_auto_confirm"):
            return res

        to_process = self.filtered(lambda p: p.auto_confirm_pending and p.move_ids)
        if to_process:
            to_process.with_context(skip_auto_confirm=True)._auto_confirm_and_validate()
            to_process.with_context(skip_auto_confirm=True).write(
                {"auto_confirm_pending": False}
            )
        return res

    def _auto_confirm_and_validate(self):
        for picking in self:
            if picking.company_id not in self.env.companies:
                continue
            if picking.state not in ("draft", "waiting", "confirmed", "assigned"):
                continue

            picking = picking.with_company(picking.company_id)
            picking.with_context(skip_auto_validate=True).action_confirm()
            if picking.state == "confirmed":
                picking.action_assign()
            if picking.state == "assigned":
                picking.with_context(skip_backorder=True).button_validate()

    def action_confirm(self):
        res = super().action_confirm()
        if self.env.context.get("skip_auto_validate"):
            return res
        if self.env.context.get("skip_backorder") or self.env.context.get("cancel_backorder"):
            return res

        for picking in self:
            if not picking.picking_type_id or not picking.picking_type_id.auto_validate:
                continue
            if picking.state not in ("confirmed", "assigned"):
                continue
            if picking.company_id not in self.env.companies:
                continue

            picking = picking.with_company(picking.company_id)
            if picking.state == "confirmed":
                picking.action_assign()

            if picking.state == "assigned":
                picking.with_context(skip_backorder=True).button_validate()

        return res

    def button_validate(self):
        return super(StockPicking, self.with_context(skip_auto_validate=True)).button_validate()
