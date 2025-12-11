/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { formatFloat } from "@web/views/fields/formatters";

patch(ListController.prototype, {

    getProductQuantity() {
        let total_qty = 0;

        const selection = this.model?.root?.selection || [];

        for (const rec of selection) {
            total_qty += rec?.data?.qty_available || 0;
        }

        return formatFloat(total_qty, { digits: [16, 2] });
    },

    get isVisibleQuantity() {
        const root = this.model?.root;
        
        return (
            root?.resModel === "product.product" &&
            (root.selection?.length || 0) > 0
        );
    },

});