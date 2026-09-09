# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Fix the protected template, preserving its copy and translations."""
    cr.execute("""
        UPDATE mail_template AS template
           SET body_html = (
               SELECT jsonb_object_agg(lang, replace(body, %s, %s))
                 FROM jsonb_each_text(template.body_html) AS content(lang, body)
           )
          FROM ir_model_data AS data
         WHERE data.module = 'sng_entrega_regalias'
           AND data.name = 'mail_template_regalia_created'
           AND data.model = 'mail.template'
           AND data.res_id = template.id
           AND template.body_html IS NOT NULL
    """, (
        "object.get_base_url()",
        "object.env['ir.config_parameter'].sudo()"
        ".get_param('web.base.url', '').rstrip('/')",
    ))
