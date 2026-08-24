# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    template_xmlid = "email_template_cycle_count_pending_approval"
    template = env.ref(
        "sng_cycle_count.%s" % template_xmlid,
        raise_if_not_found=False,
    )
    if template:
        template.write(
            {
                "email_from": (
                    "{{ (object.company_id.email or user.email or '')"
                    ".split(';')[0].strip() }}"
                )
            }
        )

    external_id = env["ir.model.data"].search(
        [("module", "=", "sng_cycle_count"), ("name", "=", template_xmlid)],
        limit=1,
    )
    external_id.write({"noupdate": False})
