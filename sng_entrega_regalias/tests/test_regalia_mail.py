# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo import Command
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestRegaliaMail(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.email = "company@example.com"
        cls.group = cls.env.ref("sng_entrega_regalias.group_regalia_manager")
        cls.env["res.users"].with_context(active_test=False).search([
            ("groups_id", "in", cls.group.ids),
        ]).write({"groups_id": [Command.unlink(cls.group.id)]})
        cls.requester = new_test_user(
            cls.env, login="regalia_mail_requester",
            groups="base.group_user,sng_entrega_regalias.group_regalia_user,stock.group_stock_user",
            email="requester@example.com",
        )
        cls.managers = cls.env["res.users"]
        for number in range(2):
            cls.managers |= new_test_user(
                cls.env, login="regalia_mail_manager_%s" % number,
                groups="base.group_user,sng_entrega_regalias.group_regalia_manager",
                email="manager%s@example.com" % number,
            )
        cls.partner = cls.env["res.partner"].create({
            "name": "Cliente <Prueba>", "email": "client@example.com",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Obsequio", "is_storable": True,
        })
        cls.warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.company.id),
        ], limit=1)

    def _values(self, **extra):
        return {
            "partner_id": self.partner.id,
            "warehouse_id": self.warehouse.id,
            "notes": "Nota <script>alert(1)</script>",
            "line_ids": [Command.create({
                "product_id": self.product.id, "quantity": 2,
            })],
            **extra,
        }

    def _mails(self, regalias):
        return self.env["mail.mail"].search([
            ("model", "=", "sng.regalia"), ("res_id", "in", regalias.ids),
        ])

    def test_creation_queues_email_for_each_manager(self):
        with patch.object(type(self.env["mail.mail"]), "send") as send:
            regalia = self.env["sng.regalia"].with_user(self.requester).create(
                self._values()
            )
            send.assert_not_called()
        mails = self._mails(regalia)
        self.assertEqual(len(mails), 2)
        self.assertEqual(set(mails.mapped("email_to")), set(self.managers.mapped("email_formatted")))
        for mail in mails:
            self.assertEqual(mail.state, "outgoing")
            self.assertIn(regalia.name, mail.subject)
            self.assertIn(self.requester.name, mail.body_html)
            self.assertIn("Cliente &lt;Prueba&gt;", mail.body_html)
            self.assertIn(self.product.name, mail.body_html)
            self.assertNotIn("<script>", mail.body_html)
            self.assertIn("/odoo/sng.regalia/%s" % regalia.id, mail.body_html)
            self.assertFalse(mail.recipient_ids)
            self.assertFalse(mail.email_cc)
        self.assertEqual(regalia.state, "draft")
        self.assertFalse(regalia.picking_id)
        self.assertFalse(regalia.move_id)

    def test_edit_and_reset_do_not_repeat_email(self):
        regalia = self.env["sng.regalia"].with_user(self.requester).create(self._values())
        mails = self._mails(regalia)
        regalia.write({"notes": "Solicitud corregida"})
        regalia.action_cancel()
        regalia.action_draft()
        self.assertEqual(self._mails(regalia), mails)

    def test_email_link_uses_backend_instead_of_public_website(self):
        self.env["ir.config_parameter"].set_param(
            "web.base.url", "https://backend.example.com/"
        )
        with patch.object(
            type(self.env["sng.regalia"]), "get_base_url",
            return_value="https://public-shop.example.com",
        ):
            regalia = self.env["sng.regalia"].with_user(self.requester).create(
                self._values()
            )
        for mail in self._mails(regalia):
            self.assertIn(
                "https://backend.example.com/odoo/sng.regalia/%s" % regalia.id,
                mail.body_html,
            )
            self.assertNotIn("public-shop.example.com", mail.body_html)

    def test_ineligible_managers_do_not_receive_email(self):
        other_company = self.env["res.company"].create({"name": "Otra compañía regalías"})
        cases = [
            {"active": False},
            {"email": False},
            {"company_id": other_company.id, "company_ids": [Command.set(other_company.ids)]},
        ]
        for values in cases:
            with self.subTest(values=values), self.cr.savepoint():
                original_values = {
                    "active": True,
                    "email": "manager0@example.com",
                    "company_id": self.company.id,
                    "company_ids": [Command.set(self.company.ids)],
                }
                manager = self.managers[0]
                manager.write(values)
                regalia = self.env["sng.regalia"].with_user(self.requester).create(self._values())
                mails = self._mails(regalia)
                self.assertEqual(len(mails), 1)
                self.assertEqual(mails.email_to, self.managers[1].email_formatted)
                manager.write(original_values)

    def test_no_managers_still_creates_draft(self):
        self.managers.write({"email": False})
        regalia = self.env["sng.regalia"].with_user(self.requester).create(self._values())
        self.assertEqual(regalia.state, "draft")
        self.assertFalse(self._mails(regalia))

    def test_batch_creation_only_notifies_drafts(self):
        regalias = self.env["sng.regalia"].with_user(self.requester).create([
            self._values(), self._values(), self._values(state="cancel"),
        ])
        self.assertEqual(len(self._mails(regalias)), 4)
        self.assertFalse(self._mails(regalias[2]))

    def test_rollback_also_discards_email(self):
        regalia_ids = []
        with self.assertRaisesRegex(ValueError, "Abort request"):
            with self.cr.savepoint():
                regalia = self.env["sng.regalia"].with_user(self.requester).create(self._values())
                regalia_ids = regalia.ids
                self.assertEqual(len(self._mails(regalia)), 2)
                raise ValueError("Abort request")
        self.assertFalse(self._mails(self.env["sng.regalia"].browse(regalia_ids)))
