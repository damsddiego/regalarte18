# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.osv import expression

class ResPartner(models.Model):
    _inherit = "res.partner"

    client_code = fields.Char(
        string="Código Cliente",
        index=True,
        copy=False,
        readonly=True
    )

    _sql_constraints = [
        ('client_code_uniq', 'unique(client_code)', 'El Código Cliente debe ser único.')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        # Asignar código por compañía sólo a quienes no traen client_code
        sequences_by_company = {}
        for partner in partners:
            if not partner.client_code:
                company = partner.company_id or self.env.company
                # cache por compañía para evitar overhead por llamada
                env_with_company = sequences_by_company.get(company.id)
                if not env_with_company:
                    env_with_company = self.env['ir.sequence'].with_company(company)
                    sequences_by_company[company.id] = env_with_company
                partner.client_code = env_with_company.next_by_code('res.partner.client.code') or '/'
        return partners

    def name_get(self):
        res = []
        for partner in self:
            name = partner.name or ''
            if partner.client_code:
                name = f"[{partner.client_code}] {name}"
            res.append((partner.id, name))
        return res

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            domain = ['|', ('client_code', operator, name), ('name', operator, name)]
            partners = self.search(domain + args, limit=limit)
            return partners.name_get()
        return super().name_search(name=name, args=args, operator=operator, limit=limit)


    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        args = args or []

        if not name:
            return super()._name_search(
                name=name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid
            )

        domain = ['|',
                  ('client_code', operator, name),
                  ('name', operator, name)]

        domain = expression.AND([domain, args])

        return super()._name_search(
            name='', args=domain, operator=operator, limit=limit, name_get_uid=name_get_uid
        )
