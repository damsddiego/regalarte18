/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { StockReportSearchModel } from "@stock/views/search/stock_report_search_model";

/**
 * Reporte Inventario > Informes > Existencias: permite calcular las cantidades
 * para un grupo de almacenes (sng.warehouse.group) o para varios almacenes a la vez.
 *
 * `product.product._get_domain_locations` ya acepta una lista de ids en el
 * contexto `warehouse_id`; aquí solo se arma esa lista desde el panel.
 */
patch(StockReportSearchModel.prototype, {
    async _loadWarehouses() {
        await super._loadWarehouses(...arguments);
        this.warehouseGroups = await this.orm.call(
            "sng.warehouse.group",
            "get_stock_report_groups",
            [],
            { context: this.context }
        );
    },

    getWarehouseGroups() {
        return this.warehouseGroups || [];
    },

    /**
     * @param {number[]} warehouseIds
     * Pone en el contexto la lista de almacenes; con un solo id se conserva el
     * comportamiento nativo (entero), con varios se envía la lista.
     */
    applyWarehousesContext(warehouseIds) {
        const ids = [...new Set(warehouseIds)];
        if (!ids.length) {
            this.clearWarehouseContext();
            return;
        }
        this.globalContext["warehouse_id"] = ids.length === 1 ? ids[0] : ids;
        this._notify();
    },
});
