/** @odoo-module */
import { registry } from "@web/core/registry";
import { download } from "@web/core/network/download";

registry.category("ir.actions.report handlers").add("comparativo_xlsx", async (action) => {
    if (action.report_type === "comparativo_xlsx") {
        await download({
            url: "/comparativo_ventas/xlsx",
            data: action.data,
        });
    }
});
