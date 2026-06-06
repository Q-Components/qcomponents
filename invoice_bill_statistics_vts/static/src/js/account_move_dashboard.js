/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";

class AccountMoveDashboardBanner extends Component {
    static template = "account_move.AccountMoveDashboardBanner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService('action')
        this.state = useState({
            today_amount: 0,
            weekly_amount: 0,
            monthly_amount:0,
            partial_paid: 0,
            unpaid: 0,
            overdue: 0,
            currency_symbol: '$',
        });
        onWillStart(async () => {
            const moveType = this.env.searchModel.context.default_move_type;
            const result = await this.orm.call(
                "account.move",
                "get_account_move_dashboard_data",
                [moveType]
            );
            Object.assign(this.state, result);
        });
    }
    async openAction(methodName) {
    const moveType = this.env.searchModel.context.default_move_type;

    const action = await this.orm.call(
        "account.move",
        methodName,
        [moveType]
    );

    this.action.doAction(action);
}
}

class AccountMoveListRenderer extends ListRenderer {
    static template = "account_move.AccountMoveListRenderer";
    static components = {
        ...ListRenderer.components,
        AccountMoveDashboardBanner,  // ✓ register here
    };
}

export const accountMoveDashboardListView = {
    ...listView,
    Renderer: AccountMoveListRenderer,
};

registry.category("views").add("account_move_dashboard_list", accountMoveDashboardListView);



