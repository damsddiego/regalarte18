from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _send_invoices_to_hacienda(self, max_invoices=10):
        # El cron de l10n_cr enviará la factura una vez guardada la transacción.
        if self.env.context.get("sng_despacho_diferir_envio_hacienda"):
            return
        return super()._send_invoices_to_hacienda(max_invoices=max_invoices)
