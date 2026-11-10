/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { StockReportSearchPanel } from "@stock/views/search/stock_report_search_panel";

/**
 * Panel izquierdo del reporte Existencias: sección "Grupos de almacenes" y
 * selección múltiple de almacenes con casillas (más un cuadro para filtrar la
 * lista, que en Regalarte tiene cientos de almacenes).
 */
patch(StockReportSearchPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.sng = useState({
            groupId: false,
            warehouseIds: [],
            warehouseFilter: "",
        });
        this._initSelectionFromContext();
    },

    /**
     * "Inventario a la fecha" (y cualquier acción que llegue con `warehouse_id`
     * en el contexto) abre esta misma lista: se refleja esa selección en el
     * panel para que no se vea "Todos los almacenes" con un filtro activo.
     */
    _initSelectionFromContext() {
        const raw = this.env.searchModel.globalContext.warehouse_id;
        let ids = [];
        if (Array.isArray(raw)) {
            ids = raw.filter((v) => Number.isInteger(v));
        } else if (Number.isInteger(raw)) {
            ids = [raw];
        }
        if (!ids.length) {
            return;
        }
        this.sng.warehouseIds = ids;
        this.selectedWarehouse = ids.length === 1 ? ids[0] : false;
        const sorted = [...ids].sort().join(",");
        const group = this.warehouseGroups.find(
            (g) => [...g.warehouse_ids].sort().join(",") === sorted
        );
        this.sng.groupId = group ? group.id : false;
    },

    get warehouseGroups() {
        return this.env.searchModel.getWarehouseGroups();
    },

    get filteredWarehouses() {
        const term = this.sng.warehouseFilter.trim().toLowerCase();
        if (!term) {
            return this.warehouses;
        }
        return this.warehouses.filter(
            (w) =>
                (w.name || "").toLowerCase().includes(term) ||
                (w.code || "").toLowerCase().includes(term)
        );
    },

    get selectedWarehouseCount() {
        return this.sng.warehouseIds.length;
    },

    isWarehouseSelected(warehouseId) {
        return this.sng.warehouseIds.includes(warehouseId);
    },

    clearWarehouseContext() {
        super.clearWarehouseContext(...arguments);
        this.sng.groupId = false;
        this.sng.warehouseIds = [];
    },

    applyWarehouseContext(warehouseId) {
        super.applyWarehouseContext(...arguments);
        this.sng.groupId = false;
        this.sng.warehouseIds = [warehouseId];
    },

    _applySelection() {
        const ids = this.sng.warehouseIds;
        this.selectedWarehouse = ids.length === 1 ? ids[0] : false;
        this.env.searchModel.applyWarehousesContext(ids);
    },

    applyWarehouseGroupContext(group) {
        this.sng.groupId = group.id;
        this.sng.warehouseIds = [...group.warehouse_ids];
        this._applySelection();
    },

    toggleWarehouseContext(warehouseId) {
        const ids = new Set(this.sng.warehouseIds);
        if (ids.has(warehouseId)) {
            ids.delete(warehouseId);
        } else {
            ids.add(warehouseId);
        }
        this.sng.groupId = false;
        this.sng.warehouseIds = [...ids];
        this._applySelection();
    },

    onWarehouseFilterInput(ev) {
        this.sng.warehouseFilter = ev.target.value;
    },
});
