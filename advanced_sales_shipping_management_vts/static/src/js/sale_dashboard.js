/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";

class SaleDashboardBanner extends Component {
    static template = "advance_sales.SaleDashboardBanner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService('action')
        this.state = useState({
            today_sales: 0,
            weekly_sales: 0,
            monthly_sales: 0,
            pending_orders: 0,
            pending_deliveries: 0,
            currency_symbol: '$',
            overdue_quotations: 0,
        });
        onWillStart(async () => {
            const result = await this.orm.call(
                "sale.order",
                "get_dashboard_data",
                []
            );
            Object.assign(this.state, result);
        });
    }
    async openAction(methodName) {

        const action = await this.orm.call(
            "sale.order",
            methodName,
            [[]]
        );

        this.action.doAction(action);
}
}

class SaleListRenderer extends ListRenderer {
    static template = "advance_sales.SaleListRenderer";
    static components = {
        ...ListRenderer.components,
        SaleDashboardBanner,  // ✓ register here
    };
}

export const saleDashboardListView = {
    ...listView,
    Renderer: SaleListRenderer,
};

registry.category("views").add("sale_dashboard_list", saleDashboardListView);
