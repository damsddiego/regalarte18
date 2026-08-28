# -*- coding: utf-8 -*-
from . import report
from . import wizard


def uninstall_hook(env):
    """Restore the original customer statement entry points."""
    original_action = env.ref(
        'sng_customer_statement.action_customer_statement_wizard',
        raise_if_not_found=False,
    )
    original_menu = env.ref(
        'sng_customer_statement.menu_customer_statement_report',
        raise_if_not_found=False,
    )
    if original_action and original_menu:
        original_menu.write({
            'name': 'Estado de Cuenta de Clientes',
            'action': f'ir.actions.act_window,{original_action.id}',
            'active': True,
        })

    generated_menu = env.ref(
        'sng_customer_statement.menu_customer_statement_generated',
        raise_if_not_found=False,
    )
    if generated_menu:
        generated_menu.write({
            'name': 'Estados de Cuenta Generados',
            'active': True,
        })

    original_report = env.ref(
        'sng_customer_statement.action_report_customer_statement',
        raise_if_not_found=False,
    )
    partner_model = env['ir.model']._get('res.partner')
    if original_report and partner_model:
        original_report.binding_model_id = partner_model
