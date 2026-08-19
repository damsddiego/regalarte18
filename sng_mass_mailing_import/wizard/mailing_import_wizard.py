# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import email_normalize, email_split


class SngMailingImportWizard(models.TransientModel):
    _name = "sng.mailing.import.wizard"
    _description = "Importar clientes a listas de correo"

    # ------------------------------------------------------------------
    # Filtros
    # ------------------------------------------------------------------
    filter_category_ids = fields.Many2many(
        "res.partner.category",
        "sng_mail_imp_wiz_cat_rel",
        string="Etiquetas de cliente",
        help="Clientes que tengan al menos una de estas etiquetas.",
    )
    filter_route_ids = fields.Many2many(
        "sng.sales.route",
        "sng_mail_imp_wiz_route_rel",
        string="Rutas / Territorios",
    )
    filter_state_ids = fields.Many2many(
        "res.country.state",
        "sng_mail_imp_wiz_state_rel",
        string="Provincias",
        domain="[('country_id.code', '=', 'CR')]",
    )
    filter_activity_ids = fields.Many2many(
        "economic.activity",
        "sng_mail_imp_wiz_act_rel",
        string="Actividades económicas",
    )
    only_consignment = fields.Boolean(
        string="Solo clientes de consignación",
        help="Solo clientes con ubicación de consignación asignada.",
    )
    exclude_category_ids = fields.Many2many(
        "res.partner.category",
        "sng_mail_imp_wiz_excl_cat_rel",
        string="Excluir etiquetas",
        help="Se omiten los clientes que tengan alguna de estas etiquetas "
        "(p. ej. MOROSO, Ruta: Inactivos - Incobrables).",
    )
    exclude_credit_blocked = fields.Boolean(
        string="Excluir crédito bloqueado (CxC)",
        default=True,
    )
    partner_count = fields.Integer(
        string="Clientes que cumplen el filtro",
        compute="_compute_partner_count",
        help="Los contactos finales pueden ser menos: se descartan correos "
        "inválidos y se deduplica cuando varios clientes comparten correo.",
    )

    # ------------------------------------------------------------------
    # Destino
    # ------------------------------------------------------------------
    dest_mode = fields.Selection(
        [
            ("existing", "Lista existente"),
            ("new", "Crear lista nueva"),
            ("per_category", "Una lista por cada etiqueta seleccionada"),
            ("per_route", "Una lista por cada ruta seleccionada"),
        ],
        string="Destino",
        required=True,
        default="new",
    )
    mailing_list_id = fields.Many2one("mailing.list", string="Lista de correo")
    new_list_name = fields.Char(string="Nombre de la lista nueva")

    # ------------------------------------------------------------------
    # Dominio y conteo
    # ------------------------------------------------------------------
    def _get_base_domain(self):
        domain = [
            ("customer_rank", ">", 0),
            ("email", "!=", False),
        ]
        if self.exclude_credit_blocked:
            domain.append(("sng_credit_blocked", "=", False))
        if self.exclude_category_ids:
            domain.append(("category_id", "not in", self.exclude_category_ids.ids))
        if self.filter_state_ids:
            domain.append(("state_id", "in", self.filter_state_ids.ids))
        if self.filter_activity_ids:
            domain.append(("activity_id", "in", self.filter_activity_ids.ids))
        if self.only_consignment:
            domain.append(("sale_location_id", "!=", False))
        return domain

    def _get_full_domain(self):
        domain = self._get_base_domain()
        if self.filter_category_ids:
            domain.append(("category_id", "in", self.filter_category_ids.ids))
        if self.filter_route_ids:
            domain.append(("sales_route_id", "in", self.filter_route_ids.ids))
        return domain

    @api.depends(
        "filter_category_ids",
        "filter_route_ids",
        "filter_state_ids",
        "filter_activity_ids",
        "only_consignment",
        "exclude_category_ids",
        "exclude_credit_blocked",
    )
    def _compute_partner_count(self):
        for wizard in self:
            wizard.partner_count = self.env["res.partner"].search_count(
                wizard._get_full_domain()
            )

    # ------------------------------------------------------------------
    # Importación
    # ------------------------------------------------------------------
    def action_import(self):
        self.ensure_one()
        Partner = self.env["res.partner"]
        lists = self.env["mailing.list"]
        created = updated = 0

        if self.dest_mode == "existing":
            if not self.mailing_list_id:
                raise UserError(_("Seleccione la lista de correo de destino."))
            partners = Partner.search(self._get_full_domain())
            c, u = self._import_partners(partners, self.mailing_list_id)
            created, updated = created + c, updated + u
            lists |= self.mailing_list_id

        elif self.dest_mode == "new":
            if not self.new_list_name:
                raise UserError(_("Indique el nombre de la lista nueva."))
            partners = Partner.search(self._get_full_domain())
            mlist = self.env["mailing.list"].create({"name": self.new_list_name})
            c, u = self._import_partners(partners, mlist)
            created, updated = created + c, updated + u
            lists |= mlist

        elif self.dest_mode == "per_category":
            if not self.filter_category_ids:
                raise UserError(
                    _("Seleccione al menos una etiqueta para crear listas por etiqueta.")
                )
            for category in self.filter_category_ids:
                domain = self._get_base_domain()
                domain.append(("category_id", "in", category.ids))
                if self.filter_route_ids:
                    domain.append(("sales_route_id", "in", self.filter_route_ids.ids))
                partners = Partner.search(domain)
                if not partners:
                    continue
                mlist = self._find_or_create_list(category.name)
                c, u = self._import_partners(partners, mlist)
                created, updated = created + c, updated + u
                lists |= mlist

        elif self.dest_mode == "per_route":
            if not self.filter_route_ids:
                raise UserError(
                    _("Seleccione al menos una ruta para crear listas por ruta.")
                )
            for route in self.filter_route_ids:
                domain = self._get_base_domain()
                domain.append(("sales_route_id", "in", route.ids))
                if self.filter_category_ids:
                    domain.append(("category_id", "in", self.filter_category_ids.ids))
                partners = Partner.search(domain)
                if not partners:
                    continue
                mlist = self._find_or_create_list(route.name)
                c, u = self._import_partners(partners, mlist)
                created, updated = created + c, updated + u
                lists |= mlist

        return {
            "type": "ir.actions.act_window",
            "name": _(
                "Contactos importados (%(created)s nuevos, %(updated)s actualizados)",
                created=created,
                updated=updated,
            ),
            "res_model": "mailing.contact",
            "view_mode": "list,form",
            "domain": [("list_ids", "in", lists.ids)],
            "context": {"default_list_ids": lists.ids},
        }

    def _find_or_create_list(self, name):
        MailingList = self.env["mailing.list"]
        mlist = MailingList.search([("name", "=", name)], limit=1)
        return mlist or MailingList.create({"name": name})

    def _partner_marketing_email(self, partner):
        """El campo email suele traer varios correos separados por ';' o ','
        (correo del cliente + copia interna). Devuelve el primer correo válido
        que no sea del dominio propio de la compañía; si todos son del dominio
        propio, el primero válido."""
        candidates = [email_normalize(e) for e in email_split(partner.email or "")]
        candidates = [e for e in candidates if e]
        if not candidates:
            return False
        own_domain = (self.env.company.email or "").rpartition("@")[2].lower()
        if own_domain:
            external = [e for e in candidates if not e.endswith("@" + own_domain)]
            if external:
                return external[0]
        return candidates[0]

    def _import_partners(self, partners, mailing_list):
        """Crea o actualiza mailing.contact para cada cliente y lo suscribe a la
        lista. Deduplica por correo normalizado. Devuelve (creados, actualizados)."""
        Contact = self.env["mailing.contact"]
        created = updated = 0
        seen_emails = set()

        # Contactos ya existentes por correo normalizado (de cualquier lista)
        emails = [e for e in (self._partner_marketing_email(p) for p in partners) if e]
        existing = Contact.search([("email_normalized", "in", emails)])
        by_email = {}
        for contact in existing:
            by_email.setdefault(contact.email_normalized, contact)

        for partner in partners:
            email = self._partner_marketing_email(partner)
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)

            contact = by_email.get(email)
            if contact:
                vals = {}
                if not contact.partner_id:
                    vals["partner_id"] = partner.id
                if mailing_list not in contact.list_ids:
                    vals["list_ids"] = [fields.Command.link(mailing_list.id)]
                if vals:
                    contact.write(vals)
                updated += 1
            else:
                Contact.create(
                    {
                        "name": partner.commercial_name or partner.name,
                        "company_name": partner.commercial_name
                        and partner.name
                        or False,
                        "email": email,
                        "partner_id": partner.id,
                        "country_id": partner.country_id.id,
                        "tag_ids": [fields.Command.set(partner.category_id.ids)],
                        "list_ids": [fields.Command.link(mailing_list.id)],
                    }
                )
                created += 1
        return created, updated
