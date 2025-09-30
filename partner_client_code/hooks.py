# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def _ensure_env_from_args(args):
    # Odoo 18: post_init_hook(env) -> args = (env,)
    if len(args) == 1:
        env = args[0]
        return env
    # Odoo 17: post_init_hook(cr, registry) -> args = (cr, registry)
    if len(args) >= 2:
        cr = args[0]
        return api.Environment(cr, SUPERUSER_ID, {})
    raise RuntimeError("Unsupported post_init_hook call signature")

def post_init_hook(*args, **kwargs):
    env = _ensure_env_from_args(args)

    seq_model = env['ir.sequence']
    template = seq_model.search([('code', '=', 'res.partner.client.code'), ('company_id', '=', False)], limit=1)
    if not template:
        return
    companies = env['res.company'].search([])
    for company in companies:
        exists = seq_model.search([
            ('code', '=', 'res.partner.client.code'),
            ('company_id', '=', company.id)
        ], limit=1)
        if not exists:
            seq_model.create({
                'name': f"Secuencia Código Cliente - {company.display_name}",
                'code': 'res.partner.client.code',
                'prefix': template.prefix or '',
                'padding': template.padding or 5,
                'implementation': template.implementation or 'no_gap',
                'company_id': company.id,
            })
