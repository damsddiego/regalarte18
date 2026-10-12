# -*- coding: utf-8 -*-
import uuid

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestInventarioMovil(TransactionCase):
    """Las tabletas comparten un usuario de Odoo (``bodega``); lo que identifica
    quién contó es la tableta."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].create({"name": "Prueba inventario móvil", "code": "TIMV"})
        cls.stock = cls.warehouse.lot_stock_id
        cls.estante = cls.env["stock.location"].create({
            "name": "Estante A", "location_id": cls.stock.id, "usage": "internal", "barcode": "TIMV-EA",
        })

        def producto(nombre, codigo, costo):
            return cls.env["product.product"].create({
                "name": nombre, "default_code": codigo, "is_storable": True, "standard_price": costo,
            })
        cls.taza = producto("Taza prueba", "9990000000011", 1000)
        cls.llavero = producto("Llavero prueba", "99900002", 500)
        cls.iman = producto("Imán prueba", "9990000000035", 300)
        Quant = cls.env["stock.quant"]
        Quant._update_available_quantity(cls.taza, cls.stock, 10)
        Quant._update_available_quantity(cls.llavero, cls.estante, 5)
        Quant._update_available_quantity(cls.iman, cls.stock, 4)

        def usuario(login, grupos):
            return cls.env["res.users"].create({
                "name": login, "login": login, "email": "%s@example.com" % login,
                "groups_id": [Command.set([cls.env.ref(g).id for g in grupos])],
            })
        cls.bodega = usuario("timv_bodega", ["sng_inventario_movil.group_contador"])
        cls.responsable = usuario("timv_responsable", ["sng_inventario_movil.group_responsable"])
        cls.gerente = usuario("timv_gerente", [
            "sng_inventario_movil.group_responsable", "stock.group_stock_manager",
            "sng_inventory_adjustment_history.group_inventory_adjustment_approver",
        ])
        Dispositivo = cls.env["sng.inventario.dispositivo"].with_user(cls.bodega)
        cls.t1, cls.t2, cls.t3 = (str(uuid.uuid4()) for _ in range(3))
        for codigo, nombre in ((cls.t1, "Tableta 1"), (cls.t2, "Tableta 2"), (cls.t3, "Tableta 3")):
            Dispositivo.app_registrar_dispositivo(codigo, nombre, "1.1.0")
        cls.tableta = {c: cls.env["sng.inventario.dispositivo"].search([("codigo", "=", c)])
                       for c in (cls.t1, cls.t2, cls.t3)}

    def _sesion(self, **vals):
        valores = {"warehouse_id": self.warehouse.id, "location_id": self.stock.id}
        valores.update(vals)
        sesion = self.env["sng.inventario.sesion"].with_user(self.responsable).create(valores)
        sesion.action_iniciar_conteo()
        return sesion

    def _lectura(self, producto, qty, ubicacion=None, ronda=1, **extra):
        return dict({
            "uuid": str(uuid.uuid4()), "product_id": producto.id,
            "location_id": (ubicacion or self.stock).id, "qty": qty, "ronda": ronda,
            "codigo": producto.default_code, "coincidencia": "referencia",
            "fecha": "2026-10-08T15:30:00Z",
        }, **extra)

    def _api(self, usuario=None):
        return self.env["sng.inventario.sesion"].with_user(usuario or self.bodega)

    def _registrar(self, sesion, tableta, lecturas, usuario=None):
        return self._api(usuario).app_registrar(sesion.id, lecturas, tableta)

    def _linea(self, sesion, producto, ubicacion=None):
        return sesion.linea_ids.filtered(
            lambda l: l.product_id == producto and l.location_id == (ubicacion or self.stock))

    def _cerrar_todo(self, sesion):
        sesion.with_user(self.responsable).action_cerrar_conteo()
        if sesion.state == "reconteo":
            sesion.with_user(self.responsable).action_cerrar_reconteo()

    def test_registro_de_tabletas(self):
        Dispositivo = self.env["sng.inventario.dispositivo"].with_user(self.bodega)
        # Volver a ingresar sin nombre conserva el registro y el nombre de Odoo.
        r = Dispositivo.app_registrar_dispositivo(self.t1)
        self.assertEqual(r["nombre"], "Tableta 1")
        self.assertEqual(r["id"], self.tableta[self.t1].id)
        with self.assertRaises(UserError):
            Dispositivo.app_registrar_dispositivo(str(uuid.uuid4()), "tableta 2")
        Dispositivo.app_registrar_dispositivo(self.t3, "Bodega pasillo 3")
        self.assertEqual(self.tableta[self.t3].name, "Bodega pasillo 3")
        self.assertEqual(self.tableta[self.t3].usuario_id, self.bodega)

    def test_catalogo_sin_cantidades(self):
        sesion = self._sesion()
        self.assertIn(sesion.id, [s["id"] for s in self._api().app_sesiones(self.t1)])
        catalogo = self._api().app_catalogo(sesion.id, self.t1)
        self.assertIn(self.estante.id, [u["id"] for u in catalogo["ubicaciones"]])
        producto = next(p for p in catalogo["productos"] if p["id"] == self.taza.id)
        self.assertEqual(set(producto), {"id", "nombre", "referencia", "barcode", "uom"})
        # El usuario de las tabletas no lee las líneas ni las lecturas directamente.
        with self.assertRaises(AccessError):
            self.env["sng.inventario.lectura"].with_user(self.bodega).search([])
        # Tableta desconocida o desactivada: no entra.
        with self.assertRaises(AccessError):
            self._api().app_catalogo(sesion.id, str(uuid.uuid4()))
        self.tableta[self.t3].active = False
        with self.assertRaises(AccessError):
            self._api().app_catalogo(sesion.id, self.t3)

    def test_tabletas_asignadas(self):
        sesion = self._sesion(dispositivo_ids=[Command.set(self.tableta[self.t1].ids)])
        self.assertFalse([s for s in self._api().app_sesiones(self.t2) if s["id"] == sesion.id])
        with self.assertRaises(AccessError):
            self._api().app_catalogo(sesion.id, self.t2)
        res = self._registrar(sesion, self.t2, [self._lectura(self.taza, 1)])
        self.assertFalse(res["aceptadas"])
        self.assertIn("no está asignada", res["rechazadas"][0]["motivo"])

    def test_cada_tableta_lleva_su_total(self):
        sesion = self._sesion()
        lectura = self._lectura(self.taza, 3)
        self.assertEqual(self._registrar(sesion, self.t1, [lectura])["aceptadas"], [lectura["uuid"]])
        # La app reintenta el mismo lote: no se duplica.
        self._registrar(sesion, self.t1, [lectura])
        self._registrar(sesion, self.t2, [self._lectura(self.taza, 2)])
        self.assertEqual(len(sesion.lectura_ids), 2)
        self.assertEqual(sesion.lectura_ids.dispositivo_id, self.tableta[self.t1] | self.tableta[self.t2])
        self.assertEqual(self._api().app_mis_totales(sesion.id, self.t1),
                         [{"product_id": self.taza.id, "location_id": self.stock.id, "qty": 3.0}])
        self.assertEqual(self._api().app_mis_totales(sesion.id, self.t2)[0]["qty"], 2.0)

        fuera = self.env["stock.location"].create({"name": "Fuera", "usage": "internal"})
        res = self._registrar(sesion, self.t1, [
            self._lectura(self.taza, 1, ubicacion=fuera), self._lectura(self.taza, 1, ronda=2),
        ])
        self.assertEqual(len(res["rechazadas"]), 2)

        # En el conteo, dos tabletas en el mismo producto se suman (reparten el estante).
        sesion.with_user(self.responsable).action_cerrar_conteo()
        linea = self._linea(sesion, self.taza)
        self.assertEqual(linea.conteo1, 5)
        self.assertEqual(linea.dispositivo_ids, self.tableta[self.t1] | self.tableta[self.t2])

    def test_flujo_completo_con_reconteo_en_otra_tableta(self):
        sesion = self._sesion(umbral_unidades=2)
        self._registrar(sesion, self.t1, [
            self._lectura(self.taza, 6), self._lectura(self.taza, 3),     # 9 vs 10: bajo umbral
            self._lectura(self.llavero, 2, ubicacion=self.estante),       # 2 vs 5: reconteo
            # el imán (4) no se cuenta: inventario total -> reconteo
        ])
        sesion.with_user(self.responsable).action_cerrar_conteo()
        self.assertEqual(sesion.state, "reconteo")
        self.assertFalse(self._linea(sesion, self.taza).requiere_reconteo)

        # La tableta 1 no recibe para recontar lo que ella contó.
        pendientes = lambda t: {(r["product_id"], r["location_id"])
                                for r in self._api().app_catalogo(sesion.id, t)["reconteo"]}
        self.assertEqual(pendientes(self.t1), {(self.iman.id, self.stock.id)})
        self.assertEqual(pendientes(self.t2), {(self.iman.id, self.stock.id),
                                               (self.llavero.id, self.estante.id)})
        res = self._registrar(sesion, self.t1, [self._lectura(self.llavero, 5, ubicacion=self.estante, ronda=2)])
        self.assertIn("otra tableta", res["rechazadas"][0]["motivo"])
        res = self._registrar(sesion, self.t2, [
            self._lectura(self.llavero, 5, ubicacion=self.estante, ronda=2),
            self._lectura(self.taza, 10, ronda=2),      # no se pidió recontar
        ])
        self.assertEqual(len(res["aceptadas"]), 1)

        sesion.with_user(self.responsable).action_cerrar_reconteo()
        self.assertEqual(sesion.state, "revision")
        self.assertEqual(self._linea(sesion, self.llavero, self.estante).diferencia, 0)
        self.assertEqual(self._linea(sesion, self.taza).diferencia, -1)
        self.assertEqual(self._linea(sesion, self.iman).diferencia, -4)
        self.assertEqual(sesion.valor_neto, -1000 - 1200)

        # El responsable corrige a mano; no puede tocar el conteo.
        linea_iman = self._linea(sesion, self.iman).with_user(self.responsable)
        linea_iman.qty_final = 1
        self.assertTrue(linea_iman.ajuste_manual)
        with self.assertRaises(AccessError):
            linea_iman.conteo1 = 99

        with self.assertRaises(AccessError):
            sesion.with_user(self.responsable).action_aplicar_ajuste()
        sesion.with_user(self.gerente).action_aplicar_ajuste()
        self.assertEqual(sesion.state, "aplicado")
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.taza, self.stock, strict=True), 9)
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.iman, self.stock, strict=True), 1)
        self.assertEqual(len(sesion.move_ids), 2)
        self.assertTrue(all(m.state == "done" for m in sesion.move_ids))

    def test_reconteos_distintos_no_se_suman(self):
        sesion = self._sesion()
        self._registrar(sesion, self.t1, [self._lectura(self.llavero, 2, ubicacion=self.estante)])
        sesion.with_user(self.responsable).action_cerrar_conteo()
        self._registrar(sesion, self.t2, [self._lectura(self.llavero, 5, ubicacion=self.estante, ronda=2)])
        self._registrar(sesion, self.t3, [self._lectura(self.llavero, 4, ubicacion=self.estante, ronda=2)])
        sesion.with_user(self.responsable).action_cerrar_reconteo()
        linea = self._linea(sesion, self.llavero, self.estante)
        self.assertEqual(linea.conteo2, 4, "Vale la última tableta, no la suma")
        self.assertTrue(linea.reconteo_conflicto)
        self.assertIn("Tableta 2=5", linea.nota)

    def test_resumen_provisional_en_reconteo(self):
        """Mientras se recuenta, el resumen muestra montos: lo recontado (última
        tableta) y, en lo demás, el primer conteo. Al cerrar queda igual."""
        sesion = self._sesion(umbral_unidades=2, reconteo_otra_tableta=False)
        self._registrar(sesion, self.t1, [
            self._lectura(self.taza, 9),                                  # 9 vs 10: bajo umbral
            self._lectura(self.llavero, 2, ubicacion=self.estante),       # 2 vs 5: reconteo
            # el imán (4) no se cuenta: reconteo
        ])
        sesion.with_user(self.responsable).action_cerrar_conteo()
        self.assertEqual(sesion.state, "reconteo")
        self.assertEqual(self._linea(sesion, self.taza).diferencia, -1)
        self.assertEqual(self._linea(sesion, self.llavero, self.estante).diferencia, -3)
        self.assertEqual(self._linea(sesion, self.iman).diferencia, -4)
        self.assertEqual(sesion.valor_faltante, -1000 - 1500 - 1200)
        self.assertIn(self.taza.categ_id.complete_name, sesion.resumen_categorias_html or "")

        self._registrar(sesion, self.t2, [self._lectura(self.llavero, 6, ubicacion=self.estante, ronda=2)])
        self.assertEqual(self._linea(sesion, self.llavero, self.estante).diferencia, 1)
        # Otra tableta recuenta el mismo producto: vale la última, no la suma.
        self._registrar(sesion, self.t3, [self._lectura(self.llavero, 5, ubicacion=self.estante, ronda=2)])
        self.assertEqual(self._linea(sesion, self.llavero, self.estante).diferencia, 0)
        self.assertEqual(sesion.valor_neto, -1000 - 1200)

        sesion.with_user(self.responsable).action_cerrar_reconteo()
        self.assertEqual(sesion.state, "revision")
        self.assertEqual(sesion.valor_neto, -1000 - 1200)

    def test_una_sola_tableta_puede_recontar(self):
        sesion = self._sesion(reconteo_otra_tableta=False)
        self._registrar(sesion, self.t1, [self._lectura(self.taza, 7)])
        sesion.with_user(self.responsable).action_cerrar_conteo()
        res = self._registrar(sesion, self.t1, [self._lectura(self.taza, 10, ronda=2)])
        self.assertEqual(len(res["aceptadas"]), 1)

    def test_movimiento_durante_el_conteo(self):
        """Una venta entre el conteo y el ajuste no se 'devuelve' al aplicar."""
        sesion = self._sesion(tipo="parcial")
        self._registrar(sesion, self.t1, [self._lectura(self.taza, 8)])   # sistema 10
        self.env["stock.quant"]._update_available_quantity(self.taza, self.stock, -3)  # se venden 3
        self._cerrar_todo(sesion)
        sesion.with_user(self.gerente).action_aplicar_ajuste()
        # Faltaban 2 al contar; después salieron 3: 10 - 3 - 2 = 5.
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.taza, self.stock, strict=True), 5)
        # Parcial: lo no contado no se toca.
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.iman, self.stock, strict=True), 4)

    def test_faltante_con_reserva_de_entrega(self):
        """Si el conteo queda por debajo de lo reservado se liberan las reservas,
        se aplica y se vuelve a reservar lo que queda."""
        self.env.company.no_negative_stock = True
        clientes = self.env.ref("stock.stock_location_customers")
        entrega = self.env["stock.picking"].create({
            "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.stock.id,
            "location_dest_id": clientes.id,
            "move_ids": [Command.create({
                "name": "Entrega", "product_id": self.taza.id, "product_uom_qty": 8,
                "product_uom": self.taza.uom_id.id, "location_id": self.stock.id,
                "location_dest_id": clientes.id,
            })],
        })
        entrega.action_confirm()
        entrega.action_assign()
        self.assertEqual(entrega.move_ids.quantity, 8)
        sesion = self._sesion(tipo="parcial")
        self._registrar(sesion, self.t1, [self._lectura(self.taza, 3)])   # sistema 10
        self._cerrar_todo(sesion)
        sesion.with_user(self.gerente).action_aplicar_ajuste()
        self.assertEqual(sum(self.env["stock.quant"]._gather(self.taza, self.stock, strict=True).mapped("quantity")), 3)
        self.assertEqual(entrega.move_ids.quantity, 3, "Se vuelve a reservar lo que quedó")
        self.assertIn(entrega.name, sesion.message_ids[0].body)

    def test_quien_conto_no_aplica(self):
        sesion = self._sesion()
        self._registrar(sesion, self.t1, [self._lectura(self.taza, 1)], usuario=self.gerente)
        self._cerrar_todo(sesion)
        with self.assertRaises(AccessError):
            sesion.with_user(self.gerente).action_aplicar_ajuste()

    def test_avance_en_vivo(self):
        sesion = self._sesion()
        self._registrar(sesion, self.t1, [self._lectura(self.taza, 6), self._lectura(self.taza, 2)])  # 8 de 10
        self._registrar(sesion, self.t2, [self._lectura(self.llavero, 7, ubicacion=self.estante)])     # 7 de 5
        filas = {(f.product_id, f.location_id): f for f in
                 self.env["sng.inventario.avance"].search([("sesion_id", "=", sesion.id)])}
        taza = filas[(self.taza, self.stock)]
        self.assertEqual((taza.estado, taza.contado, taza.sistema, taza.diferencia), ("contado", 8, 10, -2))
        self.assertEqual(taza.valor_diferencia, -2000)
        self.assertEqual(taza.dispositivo_id, self.tableta[self.t1])
        self.assertEqual(filas[(self.llavero, self.estante)].diferencia, 2)
        iman = filas[(self.iman, self.stock)]
        self.assertEqual((iman.estado, iman.diferencia), ("pendiente", -4))
        sesion.invalidate_recordset()
        self.assertEqual((sesion.avance_contados, sesion.avance_pendientes), (2, 1))
        self.assertAlmostEqual(sesion.avance_porcentaje, 200 / 3)
        self.assertEqual(sesion.avance_faltante, -2000 - 1200)
        self.assertEqual(sesion.avance_sobrante, 1000)
        self.assertEqual(sesion.avance_valor_pendiente, 1200)
        self.assertEqual(sesion.avance_tabletas, 2)
        # Las tabletas no pueden leer el avance.
        with self.assertRaises(AccessError):
            self.env["sng.inventario.avance"].with_user(self.bodega).search([])
        # Al cerrar el conteo, el avance desaparece y quedan las líneas.
        sesion.with_user(self.responsable).action_cerrar_conteo()
        self.assertFalse(self.env["sng.inventario.avance"].search([("sesion_id", "=", sesion.id)]))

    def test_resumen_por_categoria(self):
        tazas = self.env["product.category"].create({"name": "Tazas TIMV"})
        imanes = self.env["product.category"].create({"name": "Imanes TIMV"})
        self.taza.categ_id = tazas
        self.llavero.categ_id = tazas
        self.iman.categ_id = imanes
        sesion = self._sesion(tipo="parcial", reconteo_otra_tableta=False)
        self._registrar(sesion, self.t1, [
            self._lectura(self.taza, 7),                              # -3 x 1000
            self._lectura(self.llavero, 6, ubicacion=self.estante),   # +1 x 500
            self._lectura(self.iman, 2),                              # -2 x 300
        ])
        self._cerrar_todo(sesion)
        filas = {f["categoria"]: f for f in sesion._resumen_por_categoria()}
        t = filas["All / Tazas TIMV"] if "All / Tazas TIMV" in filas else filas["Tazas TIMV"]
        self.assertEqual((t["productos"], t["unidades_faltante"], t["unidades_sobrante"]), (2, -3, 1))
        self.assertEqual((t["valor_faltante"], t["valor_sobrante"], t["valor_neto"]), (-3000, 500, -2500))
        # Primero la categoría que más pierde.
        self.assertEqual(sesion._resumen_por_categoria()[0]["valor_neto"], -2500)
        self.assertEqual((sesion.unidades_faltante, sesion.unidades_sobrante), (-5, 1))
        self.assertIn("Tazas TIMV", sesion.resumen_categorias_html)
        html, _tipo = self.env["ir.actions.report"]._render_qweb_html(
            "sng_inventario_movil.report_acta_inventario", sesion.ids)
        self.assertIn(b"Ajuste por categor", html)
        accion = sesion.with_context(agrupar_categoria=1).action_ver_diferencias()
        self.assertEqual(accion["context"]["search_default_group_categ"], 1)

    def test_sesiones_superpuestas(self):
        self._sesion()
        with self.assertRaises(UserError):
            self._sesion(location_id=self.estante.id)

    def test_guardar_codigos(self):
        sesion = self._sesion(tipo="parcial")
        self._registrar(sesion, self.t1, [
            self._lectura(self.taza, 1, codigo="9990000000013", coincidencia="aproximada"),
            self._lectura(self.llavero, 1, ubicacion=self.estante, codigo="X1", coincidencia="manual"),
            self._lectura(self.llavero, 1, ubicacion=self.estante, codigo="X2", coincidencia="manual"),
        ])
        self._cerrar_todo(sesion)
        sesion.with_user(self.responsable).action_guardar_codigos()
        self.assertEqual(self.taza.barcode, "9990000000013")
        self.assertFalse(self.llavero.barcode, "Dos códigos distintos: no se adivina")
