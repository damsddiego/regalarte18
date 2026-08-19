from odoo import models, fields, api
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = 'res.partner'

    commercial_name = fields.Char(
        string='Nombre Comercial',
        help='Nombre comercial del contacto',
    )

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        partners = self.search(
            expression.AND([[('commercial_name', operator, name)], args]),
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
