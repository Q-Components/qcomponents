/** @odoo-module **/

import { UserMenu } from "@web/webclient/user_menu/user_menu";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
const userMenuRegistry = registry.category("user_menuitems");



patch(UserMenu.prototype, "advanced_email_configurator.user_menu", {
    setup() {
        this._super.apply(this, arguments);
        userMenuRegistry.remove("odoo_account")
        userMenuRegistry.remove("documentation")
        userMenuRegistry.remove("support")
    },

});
