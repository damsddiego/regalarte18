# -*- coding: utf-8 -*-
import logging

from odoo import api, Command, SUPERUSER_ID


_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env["sng.cycle.count.line"].search([])
    for line in lines:
        cost = line.product_id.with_company(line.company_id).standard_price
        line.write({"unit_cost": cost})

    management_group = env.ref("sng_cycle_count.group_cycle_count_management")
    management_user = env["res.users"].search(
        [("login", "=", "gerencia@regalartecr.com")],
        limit=1,
    )
    if management_user:
        management_group.write({"users": [Command.link(management_user.id)]})
        _logger.info(
            "Assigned %s to Gerencia de Conteos Cíclicos.",
            management_user.display_name,
        )
    else:
        _logger.warning(
            "User gerencia@regalartecr.com was not found; the cycle count management group remains unassigned."
        )
