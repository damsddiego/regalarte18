/** @odoo-module **/

import { registry } from "@web/core/registry";
import { download } from "@web/core/network/download";

registry.category("ir.actions.report handlers").add("xlsx", async function (action) {
    if (action.report_type === 'xlsx') {
        const type = action.report_type;
        let url = `/report/${type}/${action.report_name}`;
        const actionOptions = action.data;
        if (actionOptions) {
            const options = encodeURIComponent(JSON.stringify(actionOptions));
            const context = encodeURIComponent(JSON.stringify(action.context || {}));
            url += `?options=${options}&context=${context}`;
        }
        try {
            await download({
                url: '/report/download',
                data: {
                    data: JSON.stringify([url, action.report_type]),
                    context: JSON.stringify(action.context || {}),
                },
            });
        } catch (error) {
            console.error('Error downloading XLSX report:', error);
        }
        return true;
    }
    return false;
});
