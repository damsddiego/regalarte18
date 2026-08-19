# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def action_open_stock_by_customer_report(self):
        self.ensure_one()
        partner = self.commercial_partner_id

        if not partner.sale_location_id:
            raise UserError('Este contacto no tiene una ubicación de venta asignada.')

        wizard = self.env['stock.by.customer.wizard'].create({
            'company_id': partner.company_id.id or self.env.company.id,
            'date_report': fields.Date.context_today(self),
            'location_ids': [(6, 0, [partner.sale_location_id.id])],
        })
        return wizard.action_generate_report()
