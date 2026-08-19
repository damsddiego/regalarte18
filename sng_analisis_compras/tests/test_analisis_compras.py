# -*- coding: utf-8 -*-
import math
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


class TestAnalisisComprasHelpers(TransactionCase):
    """Tests de unidad: helpers de fechas, outliers y constrains."""

    def _wizard(self, **vals):
        base = {"date_from": "2026-04-01", "date_to": "2026-04-16", "coverage_months": 1.0}
        base.update(vals)
        return self.env["sng.analisis.compras.wizard"].create(base)

    def test_analysis_days_is_inclusive(self):
        self.assertEqual(self._wizard()._get_analysis_days(), 16)

    def test_analysis_months_is_days_over_30(self):
        wizard = self._wizard(date_from="2026-04-01", date_to="2026-05-30")
        self.assertAlmostEqual(wizard._get_analysis_months(), 2.0)

    def test_avg_calculation_days_clamps_to_operations_start(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sng_analisis_compras.operations_start_date", "2026-04-01"
        )
        wizard = self._wizard(date_from="2026-01-01", date_to="2026-04-30")
        self.assertEqual(wizard._get_analysis_days(), 120)
        # El promedio solo cuenta desde el inicio de operaciones (30 días de abril).
        self.assertEqual(wizard._get_avg_calculation_days(), 30)

    def test_avg_calculation_days_within_operations_period(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sng_analisis_compras.operations_start_date", "2026-04-01"
        )
        self.assertEqual(self._wizard()._get_avg_calculation_days(), 16)

    def test_operations_start_date_invalid_param_falls_back(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sng_analisis_compras.operations_start_date", "no-es-fecha"
        )
        wizard = self._wizard()
        self.assertEqual(wizard._get_operations_start_date(), date(2026, 4, 1))

    def test_month_starts_cross_year_boundary(self):
        wizard = self._wizard(date_from="2026-02-01", date_to="2026-02-10")
        self.assertEqual(
            wizard._get_month_starts(),
            [
                date(2025, 9, 1), date(2025, 10, 1), date(2025, 11, 1),
                date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1),
            ],
        )

    def test_month_labels_in_spanish(self):
        wizard = self._wizard(date_from="2026-07-01", date_to="2026-07-16")
        labels = wizard._get_month_labels()
        self.assertEqual(labels[0], "Febrero 2026")
        self.assertEqual(labels[-1], "Julio 2026")

    def test_warehouse_group_selects_warehouses(self):
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "in", self.env.companies.ids)], limit=2
        )
        group = self.env["sng.warehouse.group"].create(
            {"name": "Principales", "warehouse_ids": [(6, 0, warehouses.ids)]}
        )
        wizard = self._wizard(warehouse_group_id=group.id)
        self.assertEqual(wizard._get_selected_warehouses(), warehouses)
        self.assertEqual(wizard._get_filter_summary()["warehouse_group"], group.display_name)

    def test_product_report_name_excludes_default_code(self):
        product = self.env["product.product"].create(
            {"name": "Producto para reporte", "default_code": "COD-REPORTE"}
        )
        self.assertEqual(
            self._wizard()._get_product_report_name(product), "Producto para reporte"
        )

    def test_outlier_detected_when_current_avg_exceeds_threshold(self):
        wizard = self._wizard(outlier_threshold=2.0, min_history_months=2)
        self.assertTrue(wizard._is_product_outlier(1, 100.0, {1: [10.0, 12.0, 11.0]}))

    def test_outlier_not_detected_within_normal_range(self):
        wizard = self._wizard(outlier_threshold=2.0, min_history_months=2)
        self.assertFalse(wizard._is_product_outlier(1, 11.0, {1: [10.0, 12.0, 11.0]}))

    def test_outlier_not_detected_with_insufficient_history(self):
        wizard = self._wizard(outlier_threshold=2.0, min_history_months=2)
        self.assertFalse(wizard._is_product_outlier(1, 1000.0, {1: [10.0]}))

    def test_outlier_with_zero_standard_deviation(self):
        wizard = self._wizard(outlier_threshold=2.0, min_history_months=2)
        self.assertTrue(wizard._is_product_outlier(1, 11.0, {1: [10.0, 10.0]}))
        self.assertFalse(wizard._is_product_outlier(1, 10.0, {1: [10.0, 10.0]}))

    def test_dates_must_be_ordered(self):
        with self.assertRaises(ValidationError):
            self._wizard(date_from="2026-05-01", date_to="2026-04-01")

    def test_coverage_months_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self._wizard(coverage_months=-1.0)

    def test_outlier_threshold_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self._wizard(outlier_threshold=-1.0)

    def test_min_history_months_must_be_at_least_two(self):
        with self.assertRaises(ValidationError):
            self._wizard(min_history_months=1)

    def test_partial_month_factor(self):
        # Mes completo: sin ajuste.
        wizard = self._wizard(date_to="2026-04-30")
        self.assertAlmostEqual(wizard._get_partial_month_factor(), 1.0)
        # Mes cortado al día 21: extrapolar a 30 días.
        wizard = self._wizard(date_from="2026-04-01", date_to="2026-07-21")
        self.assertAlmostEqual(wizard._get_partial_month_factor(), 30.0 / 21.0)

    def test_weighted_demand_config_all_months(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sng_analisis_compras.operations_start_date", "2026-04-01"
        )
        # date_to julio → mes_1..mes_4 = jul, jun, may, abr: todos operativos.
        wizard = self._wizard(date_from="2026-07-01", date_to="2026-07-21")
        config = dict(wizard._get_weighted_demand_config())
        self.assertEqual(set(config), {1, 2, 3, 4})
        for index, expected in ((1, 0.4), (2, 0.3), (3, 0.2), (4, 0.1)):
            self.assertAlmostEqual(config[index], expected)

    def test_weighted_demand_config_renormalizes_pre_ops_months(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sng_analisis_compras.operations_start_date", "2026-04-01"
        )
        # date_to mayo → mes_3 (marzo) y mes_4 (febrero) son pre-operaciones:
        # se excluyen y los pesos 0.4/0.3 se renormalizan a 1.
        wizard = self._wizard(date_from="2026-05-01", date_to="2026-05-31")
        config = dict(wizard._get_weighted_demand_config())
        self.assertEqual(set(config), {1, 2})
        self.assertAlmostEqual(config[1], 0.4 / 0.7)
        self.assertAlmostEqual(config[2], 0.3 / 0.7)

    def test_inventory_metrics_replicates_excel_row(self):
        # Fila 38022001 del Excel de Gerson (jul-2026): σ y stock de seguridad
        # deben calzar. La demanda ponderada difiere adrede: aquí el mes
        # parcial se normaliza también en la demanda (el Excel solo en σ).
        wizard = self._wizard(
            date_from="2026-04-01", date_to="2026-07-21", coverage_months=6.0
        )
        monthly = {"mes_1": 4959.0, "mes_2": 5735.0, "mes_3": 6648.0, "mes_4": 6477.0}
        config = [(1, 0.4), (2, 0.3), (3, 0.2), (4, 0.1)]
        m = wizard._compute_inventory_metrics(
            monthly, 6.0, 20788.0, 0.0, 1.0, config, 30.0 / 21.0
        )
        self.assertAlmostEqual(m["desviacion_demanda"], 486.896, places=2)
        self.assertAlmostEqual(m["stock_seguridad"], 1967.868, places=2)
        norm_jul = 4959.0 * 30.0 / 21.0
        demanda = norm_jul * 0.4 + 5735.0 * 0.3 + 6648.0 * 0.2 + 6477.0 * 0.1
        self.assertAlmostEqual(m["demanda_ponderada"], demanda, places=4)
        self.assertAlmostEqual(m["coef_variacion"], m["desviacion_demanda"] / demanda, places=6)
        self.assertAlmostEqual(m["stock_disponible"], 20788.0)
        self.assertAlmostEqual(m["stock_proyectado"], 20788.0 - demanda * 6.0, places=2)
        self.assertAlmostEqual(m["punto_reorden"], demanda * 6.0 + m["stock_seguridad"], places=2)
        self.assertAlmostEqual(m["stock_objetivo"], demanda * 12.0 + m["stock_seguridad"], places=2)
        self.assertAlmostEqual(m["necesidad_neta"], m["stock_objetivo"] - 20788.0, places=2)
        self.assertEqual(m["compra_sugerida_ajustada"], math.ceil(m["necesidad_neta"]))
        self.assertAlmostEqual(m["cobertura_meses"], 20788.0 / demanda, places=4)
        self.assertEqual(m["exceso_unidades"], 0.0)

    def test_compra_ajustada_rounds_to_moq(self):
        wizard = self._wizard(coverage_months=1.0)
        monthly = {"mes_1": 100.0, "mes_2": 100.0, "mes_3": 100.0, "mes_4": 100.0}
        config = [(1, 0.4), (2, 0.3), (3, 0.2), (4, 0.1)]
        # Demanda constante 100, σ = 0 → objetivo = 100 × (1 + 1) = 200.
        m = wizard._compute_inventory_metrics(monthly, 1.0, 0.0, 0.0, 12.0, config, 1.0)
        self.assertAlmostEqual(m["necesidad_neta"], 200.0, places=6)
        self.assertEqual(m["compra_sugerida_ajustada"], 204.0)  # ceil(200/12) × 12
        # MOQ 0 o sin proveedor → se trata como 1.
        m = wizard._compute_inventory_metrics(monthly, 1.0, 0.0, 0.0, 0.0, config, 1.0)
        self.assertEqual(m["moq"], 1.0)
        self.assertEqual(m["compra_sugerida_ajustada"], 200.0)

    def test_estado_cascade(self):
        wizard = self._wizard()

        def metrics(**kw):
            base = dict(
                demanda_ponderada=10.0, coef_variacion=0.1, stock_disponible=100.0,
                stock_proyectado=50.0, punto_reorden=20.0, stock_objetivo=80.0,
            )
            base.update(kw)
            return base

        self.assertEqual(wizard._get_estado(0.0, 100.0, metrics()), "datos_incompletos")
        self.assertEqual(wizard._get_estado(50.0, 0.0, metrics()), "datos_incompletos")
        self.assertEqual(
            wizard._get_estado(50.0, 100.0, metrics(stock_proyectado=-1.0)), "quiebre"
        )
        # Agotado con demanda cero: también quiebre.
        self.assertEqual(
            wizard._get_estado(50.0, 100.0, metrics(
                stock_disponible=0.0, demanda_ponderada=0.0, stock_proyectado=0.0
            )),
            "quiebre",
        )
        # Agotado con demanda negativa (devoluciones netas): NO es quiebre.
        self.assertEqual(
            wizard._get_estado(50.0, 100.0, metrics(
                stock_disponible=0.0, demanda_ponderada=-5.0, stock_proyectado=10.0
            )),
            "reordenar",
        )
        self.assertEqual(
            wizard._get_estado(50.0, 100.0, metrics(stock_disponible=15.0)), "reordenar"
        )
        # El exceso manda sobre la demanda inestable (disponible > objetivo × 1.5).
        self.assertEqual(
            wizard._get_estado(50.0, 100.0, metrics(
                stock_disponible=130.0, coef_variacion=2.0
            )),
            "exceso",
        )
        self.assertEqual(
            wizard._get_estado(50.0, 100.0, metrics(coef_variacion=0.6)), "inestable"
        )
        self.assertEqual(wizard._get_estado(50.0, 100.0, metrics()), "saludable")

    def test_assign_abc(self):
        rows = [{"venta_valorizada": v} for v in (800.0, 100.0, 60.0, 40.0, 0.0)]
        self.env["sng.analisis.compras.wizard"]._assign_abc(rows)
        # 80% acumulado → A; 90% → B; después del 95% → C; sin venta → C.
        self.assertEqual([r["clase_abc"] for r in rows], ["a", "b", "c", "c", "c"])

    def test_xlsx_cell_reference(self):
        report = self.env["report.sng_analisis_compras.analisis_compras_xlsx"]
        self.assertEqual(report._xl_cell(0, 0), "A1")
        self.assertEqual(report._xl_cell(4, 2), "C5")
        self.assertEqual(report._xl_cell(9, 25), "Z10")
        self.assertEqual(report._xl_cell(9, 26), "AA10")


@tagged("post_install", "-at_install")
class TestAnalisisComprasFlow(TransactionCase):
    """Tests funcionales: facturas contabilizadas → filas del reporte.

    Usa la compañía principal de la BD (con plan contable ya cargado) en vez
    de AccountTestInvoicingCommon: crear una compañía nueva dispara una
    colisión del constraint único de client_code (partner_client_code usa
    secuencia por compañía con unicidad global).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env["ir.config_parameter"].sudo().set_param(
            "sng_analisis_compras.operations_start_date", "2026-04-01"
        )
        # cr_electronic_invoice exige un medio de pago FE en todo account.move
        cls.env.company.payment_method_default_id = cls.env.ref(
            "cr_electronic_invoice.PaymentMethods_1"
        )
        cls.partner_a = cls.env["res.partner"].create({"name": "Cliente Análisis"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Producto Análisis",
                "default_code": "ANLC-001",
                "is_storable": True,
                "purchase_ok": True,
                "sale_ok": True,
                "lst_price": 100.0,
            }
        )
        cls.product_sin_ventas = cls.env["product.product"].create(
            {
                "name": "Producto Sin Ventas",
                "default_code": "ANLC-002",
                "is_storable": True,
                "purchase_ok": True,
            }
        )

    def _post_move(self, move_type, invoice_date, quantity, product=None):
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": invoice_date,
                "invoice_line_ids": [
                    (0, 0, {
                        "product_id": (product or self.product).id,
                        "quantity": quantity,
                        "price_unit": 100.0,
                    }),
                ],
            }
        )
        move.action_post()
        return move

    def _wizard(self, **vals):
        base = {
            "date_from": "2026-06-01",
            "date_to": "2026-06-30",
            "coverage_months": 1.0,
            "product_ids": [(6, 0, (self.product | self.product_sin_ventas).ids)],
        }
        base.update(vals)
        return self.env["sng.analisis.compras.wizard"].create(base)

    def _get_row(self, rows, product):
        matches = [r for r in rows if r["product_id"] == product.id]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_invoiced_quantity_counted_in_range(self):
        self._post_move("out_invoice", "2026-06-15", 5)
        rows = self._wizard()._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertEqual(row["qty_sold"], 5.0)
        self.assertEqual(row["codigo"], "ANLC-001")
        self.assertEqual(row["descripcion"], "Producto Análisis")

    def test_credit_note_subtracts(self):
        self._post_move("out_invoice", "2026-06-15", 5)
        self._post_move("out_refund", "2026-06-20", 2)
        rows = self._wizard()._get_report_rows()
        self.assertEqual(self._get_row(rows, self.product)["qty_sold"], 3.0)

    def test_draft_invoice_not_counted(self):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-06-15",
                "invoice_line_ids": [
                    (0, 0, {"product_id": self.product.id, "quantity": 7, "price_unit": 100.0}),
                ],
            }
        )
        self.assertEqual(move.state, "draft")
        rows = self._wizard()._get_report_rows()
        self.assertEqual(self._get_row(rows, self.product)["qty_sold"], 0.0)

    def test_monthly_breakdown_places_invoice_in_correct_column(self):
        # date_to junio 2026 → mes_1 = junio, mes_2 = mayo
        self._post_move("out_invoice", "2026-06-10", 4)
        self._post_move("out_invoice", "2026-05-10", 9)
        rows = self._wizard()._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertEqual(row["mes_1"], 4.0)
        self.assertEqual(row["mes_2"], 9.0)
        self.assertEqual(row["mes_3"], 0.0)
        self.assertEqual(row["total_6m"], 13.0)
        # mayo está fuera del rango de análisis (junio)
        self.assertEqual(row["qty_sold"], 4.0)

    def test_suggested_and_qty_to_buy(self):
        # Rango de 30 días → promedio mensual = qty vendida; cobertura 2 meses.
        self._post_move("out_invoice", "2026-06-15", 6)
        rows = self._wizard(coverage_months=2.0)._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertAlmostEqual(row["promedio_mensual"], 6.0)
        self.assertAlmostEqual(row["suggested_purchase_qty"], 12.0)
        # Sin stock ni OC pendientes.
        self.assertAlmostEqual(row["qty_to_buy"], 12.0)
        self.assertEqual(row["meses_inventario"], 0.0)

    def test_only_with_sales_filters_rows(self):
        self._post_move("out_invoice", "2026-06-15", 5)
        wizard = self._wizard(only_with_sales=True)
        rows = wizard._get_report_rows()
        product_ids = {r["product_id"] for r in rows}
        self.assertIn(self.product.id, product_ids)
        self.assertNotIn(self.product_sin_ventas.id, product_ids)

    def test_product_code_filter(self):
        wizard = self._wizard(product_code="ANLC-002")
        products = wizard._get_report_products()
        self.assertEqual(products, self.product_sin_ventas)

    def test_refresh_lines_creates_and_replaces(self):
        self._post_move("out_invoice", "2026-06-15", 5)
        wizard = self._wizard()
        wizard._refresh_lines()
        self.assertEqual(len(wizard.line_ids), 2)
        wizard._refresh_lines()
        self.assertEqual(len(wizard.line_ids), 2)

    def _create_seller(self, delay, sequence=1, product=None):
        vendor = self.env["res.partner"].create(
            {"name": f"Proveedor Delay {delay}", "supplier_rank": 1}
        )
        self.env["product.supplierinfo"].create(
            {
                "partner_id": vendor.id,
                "product_tmpl_id": (product or self.product).product_tmpl_id.id,
                "sequence": sequence,
                "delay": delay,
            }
        )
        return vendor

    def test_lead_time_added_to_coverage(self):
        # delay 180 días = 6 meses; cobertura 2 → sugerido = 6 × (2 + 6) = 48
        self._create_seller(delay=180)
        self._post_move("out_invoice", "2026-06-15", 6)
        rows = self._wizard(coverage_months=2.0)._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertAlmostEqual(row["lead_time_months"], 6.0)
        self.assertAlmostEqual(row["suggested_purchase_qty"], 48.0)
        self.assertAlmostEqual(row["qty_to_buy"], 48.0)

    def test_lead_time_disabled_keeps_plain_coverage(self):
        self._create_seller(delay=180)
        self._post_move("out_invoice", "2026-06-15", 6)
        rows = self._wizard(
            coverage_months=2.0, include_lead_time=False
        )._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertAlmostEqual(row["lead_time_months"], 0.0)
        self.assertAlmostEqual(row["suggested_purchase_qty"], 12.0)

    def test_lead_time_zero_without_seller(self):
        self._post_move("out_invoice", "2026-06-15", 6)
        rows = self._wizard(coverage_months=2.0)._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertAlmostEqual(row["lead_time_months"], 0.0)
        self.assertAlmostEqual(row["suggested_purchase_qty"], 12.0)

    def test_lead_time_uses_main_seller_delay(self):
        # El plazo sale del proveedor principal (menor secuencia), no de otros.
        self._create_seller(delay=30, sequence=1)
        self._create_seller(delay=180, sequence=5)
        self._post_move("out_invoice", "2026-06-15", 6)
        rows = self._wizard(coverage_months=1.0)._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertAlmostEqual(row["lead_time_months"], 1.0)
        self.assertAlmostEqual(row["suggested_purchase_qty"], 12.0)

    def _confirm_so_and_deliver(self, ordered, delivered):
        """Pedido confirmado en junio 2026 entregando `delivered` sin backorder."""
        # sng_control_sale bloquea confirmar sin stock: abastecer primero.
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, warehouse.lot_stock_id, ordered
        )
        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "order_line": [
                    (0, 0, {
                        "product_id": self.product.id,
                        "product_uom_qty": ordered,
                        "price_unit": 100.0,
                    }),
                ],
            }
        )
        so.action_confirm()
        so.date_order = "2026-06-15 12:00:00"
        picking = so.picking_ids
        picking.move_ids.quantity = delivered
        picking.move_ids.picked = True
        res = picking.button_validate()
        if isinstance(res, dict) and res.get("res_model") == "stock.backorder.confirmation":
            self.env[res["res_model"]].with_context(res["context"]).create(
                {}
            ).process_cancel_backorder()
        return so

    def _return_delivery(self, so, quantity):
        picking = so.picking_ids.filtered(lambda p: p.state == "done")[:1]
        wizard = self.env["stock.return.picking"].with_context(
            active_id=picking.id, active_model="stock.picking"
        ).create({})
        wizard.product_return_moves.quantity = quantity
        res = wizard.action_create_returns()
        return_picking = self.env["stock.picking"].browse(res["res_id"])
        return_picking.move_ids.quantity = quantity
        return_picking.move_ids.picked = True
        return_picking.button_validate()
        return return_picking

    def test_undelivered_partial_no_backorder(self):
        so = self._confirm_so_and_deliver(ordered=10, delivered=6)
        self.assertEqual(so.order_line.qty_delivered, 6.0)
        rows = self._wizard()._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertEqual(row["qty_undelivered"], 4.0)
        # Check desactivado (default): el promedio solo usa lo facturado.
        self.assertEqual(row["promedio_mensual"], 0.0)

    def test_undelivered_included_in_average(self):
        self._confirm_so_and_deliver(ordered=10, delivered=6)
        self._post_move("out_invoice", "2026-06-15", 6)
        rows = self._wizard(include_undelivered=True)._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertEqual(row["qty_sold"], 6.0)
        self.assertEqual(row["qty_undelivered"], 4.0)
        # Rango de 30 días → 1 mes: promedio = (6 + 4) / 1.
        self.assertAlmostEqual(row["promedio_mensual"], 10.0)
        self.assertAlmostEqual(row["suggested_purchase_qty"], 10.0)

    def test_return_not_counted_as_undelivered(self):
        so = self._confirm_so_and_deliver(ordered=10, delivered=10)
        self._return_delivery(so, 2)
        # La devolución baja la cantidad entregada de la línea a 8...
        self.assertEqual(so.order_line.qty_delivered, 8.0)
        rows = self._wizard()._get_report_rows()
        # ...pero no es faltante de stock: no cuenta como no entregado.
        self.assertEqual(self._get_row(rows, self.product)["qty_undelivered"], 0.0)

    def test_sales_all_warehouses_ignores_warehouse_filter_in_sales(self):
        # Factura manual (sin pedido/entrega): no tiene almacén atribuible.
        # Con el check activo (default) cuenta aunque se filtre por almacén.
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self._post_move("out_invoice", "2026-06-15", 5)
        rows = self._wizard(
            warehouse_ids=[(6, 0, warehouse.ids)]
        )._get_report_rows()
        self.assertEqual(self._get_row(rows, self.product)["qty_sold"], 5.0)

    def test_sales_filtered_by_warehouse_when_flag_disabled(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        self._post_move("out_invoice", "2026-06-15", 5)
        rows = self._wizard(
            warehouse_ids=[(6, 0, warehouse.ids)], sales_all_warehouses=False
        )._get_report_rows()
        self.assertEqual(self._get_row(rows, self.product)["qty_sold"], 0.0)

    def test_vendor_map_uses_main_seller(self):
        vendor = self.env["res.partner"].create({"name": "Proveedor Uno", "supplier_rank": 1})
        self.env["product.supplierinfo"].create(
            {
                "partner_id": vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "sequence": 1,
            }
        )
        wizard = self._wizard()
        rows = wizard._get_report_rows()
        self.assertEqual(self._get_row(rows, self.product)["vendor_id"], vendor.id)

    def test_proveedor_filter_limits_products(self):
        vendor = self.env["res.partner"].create({"name": "Proveedor Dos", "supplier_rank": 1})
        self.env["product.supplierinfo"].create(
            {
                "partner_id": vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
            }
        )
        wizard = self._wizard(proveedor_ids=[(6, 0, vendor.ids)])
        products = wizard._get_report_products()
        self.assertEqual(products, self.product)

    def test_inventory_model_row_values(self):
        # Rango julio completo → mes_1..mes_4 = jul, jun, may, abr (todos
        # posteriores al inicio de operaciones; mes completo → sin normalizar).
        self.product.product_tmpl_id.standard_price = 40.0
        self._post_move("out_invoice", "2026-07-10", 60)
        self._post_move("out_invoice", "2026-06-10", 30)
        self._post_move("out_invoice", "2026-05-10", 90)
        rows = self._wizard(
            date_from="2026-07-01", date_to="2026-07-31"
        )._get_report_rows()
        row = self._get_row(rows, self.product)
        # demanda = 60×0.4 + 30×0.3 + 90×0.2 + 0×0.1 = 51
        self.assertAlmostEqual(row["demanda_ponderada"], 51.0)
        # σ poblacional de [60, 30, 90, 0] = √1125
        self.assertAlmostEqual(row["desviacion_demanda"], 1125 ** 0.5, places=4)
        # Sin proveedor → plazo 0 → stock de seguridad 0; cobertura 1 mes.
        self.assertAlmostEqual(row["stock_seguridad"], 0.0)
        self.assertAlmostEqual(row["punto_reorden"], 0.0)
        self.assertAlmostEqual(row["stock_objetivo"], 51.0)
        self.assertAlmostEqual(row["necesidad_neta"], 51.0)
        self.assertEqual(row["compra_sugerida_ajustada"], 51.0)
        # Disponible 0 con demanda positiva → quiebre.
        self.assertEqual(row["estado"], "quiebre")
        self.assertEqual(
            row["accion"], "Prioridad alta: emitir RFQ/OC y revisar alternativa local"
        )
        self.assertAlmostEqual(row["venta_valorizada"], 180.0 * 100.0)
        self.assertEqual(row["clase_abc"], "a")
        self.assertEqual(self._get_row(rows, self.product_sin_ventas)["clase_abc"], "c")

    def test_moq_from_seller_min_qty(self):
        self.product.product_tmpl_id.standard_price = 40.0
        vendor = self.env["res.partner"].create(
            {"name": "Proveedor MOQ", "supplier_rank": 1}
        )
        self.env["product.supplierinfo"].create(
            {
                "partner_id": vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "min_qty": 25.0,
                "delay": 0,
            }
        )
        self._post_move("out_invoice", "2026-07-10", 10)
        rows = self._wizard(
            date_from="2026-07-01", date_to="2026-07-31"
        )._get_report_rows()
        row = self._get_row(rows, self.product)
        self.assertEqual(row["moq"], 25.0)
        # demanda = 10×0.4 = 4; plazo 0 → objetivo 4; se redondea al MOQ.
        self.assertAlmostEqual(row["necesidad_neta"], 4.0)
        self.assertEqual(row["compra_sugerida_ajustada"], 25.0)
