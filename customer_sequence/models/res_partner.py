# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Aysha Shalin (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC
#    LICENSE (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from odoo import api, fields, models
from odoo.osv import expression


class ResPartner(models.Model):
    """ Inherited Partner for generating unique sequence """
    _inherit = 'res.partner'

    unique_id = fields.Char(
        string='Código cliente',
        help="The Unique Sequence no",
        default='/',
        copy=False,
        index=True,  # Index for better search performance
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Super create function for generating sequence.

        Only sets the ``unique_id`` field; no longer modifica el nombre del
        partner para evitar que el código aparezca varias veces en pantalla.
        """
        records = super(ResPartner, self).create(vals_list)
        company = self.env.company.sudo()
        for rec in records:
            if rec.unique_id == '/':
                code = company.next_code or company.customer_code
                rec.unique_id = code
                company.write({'next_code': code + 1})
        return records

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        partners = self.search(
            expression.AND([[('unique_id', operator, name)], args]),
            limit=limit,
        )
        result = [(partner.id, partner.display_name) for partner in partners.sudo()]
        remaining = limit - len(result) if limit else None
        if remaining is not None and remaining <= 0:
            return result

        found_ids = set(partners.ids)
        for partner_id, display_name in super().name_search(
            name=name, args=args, operator=operator, limit=remaining
        ):
            if partner_id not in found_ids:
                result.append((partner_id, display_name))
        return result
