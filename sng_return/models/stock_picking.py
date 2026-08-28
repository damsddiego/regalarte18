from odoo import api, fields, models


class StockPicking(models.Model):
    """Idempotencia para traslados creados por la App Ruteros (p. ej. RETC).

    La app móvil puede reenviar un create si pierde el response de un picking
    que Odoo SÍ creó (corte de red / timeout). Sin protección, eso genera un
    traslado de inventario DUPLICADO. Para evitarlo, la app envía un token
    estable por operación en [sng_idempotency_key] y aquí se deduplica:

      - create() devuelve el picking existente si la clave ya fue usada
        (reenvío) en vez de crear un duplicado.
      - un índice único parcial garantiza atomicidad incluso ante envíos
        concurrentes (lo que un search-previo en la app no puede asegurar).
    """

    _inherit = "stock.picking"

    sng_idempotency_key = fields.Char(
        string="Clave de idempotencia (App Ruteros)",
        copy=False,
        index=True,
        help="Token estable enviado por la app móvil para deduplicar reenvíos "
        "de un mismo traslado. No debe reutilizarse entre operaciones distintas.",
    )

    def init(self):
        # Índice único parcial: dos pickings NO cancelados con la misma clave no
        # pueden coexistir. Es el backstop atómico ante reenvíos concurrentes.
        # Se excluyen los cancelados para no bloquear la re-creación tras anular.
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS stock_picking_sng_idempotency_key_uniq
            ON stock_picking (sng_idempotency_key)
            WHERE sng_idempotency_key IS NOT NULL
              AND sng_idempotency_key != ''
              AND state != 'cancel'
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        pickings = self.browse()
        pending_vals = []
        for vals in vals_list:
            key = vals.get("sng_idempotency_key")
            if key:
                existing = self.search(
                    [
                        ("sng_idempotency_key", "=", key),
                        ("state", "!=", "cancel"),
                    ],
                    limit=1,
                )
                if existing:
                    # Reenvío detectado: devolver el picking ya creado.
                    pickings |= existing
                    continue
            pending_vals.append(vals)
        if pending_vals:
            pickings |= super().create(pending_vals)
        return pickings
