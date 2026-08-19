/** @odoo-module **/

import { registry } from "@web/core/registry";
import { download } from "@web/core/network/download";

registry
    .category("ir.actions.report handlers")
    .add("sng_sales_route_sales_xlsx", async (action) => {
        if (action.report_type !== "sng_sales_route_sales_xlsx") {
            return false;
        }
        await download({
            url: "/sng_sales_routes/xlsx",
            data: action.data,
        });
        return true;
    });
