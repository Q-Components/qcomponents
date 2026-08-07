import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { _t } from "@web/core/l10n/translation";

const POLL_INTERVAL_MS = 5000;
const MAX_DURATION_MS = 15 * 60 * 1000; // device codes expire ~15 min

/**
 * Auto-polls ai.oauth.wizard.action_poll on a timer while a device-code flow is
 * pending, then closes the dialog once the credential connects. Saves the user
 * from clicking "Poll" repeatedly. The manual Poll button still works as a
 * fallback.
 */
export class OAuthAutoPoll extends Component {
    static template = "open_ai_connector.OAuthAutoPoll";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ active: false });
        this._timer = null;
        this._deadline = 0;
        onWillStart(() => this._maybeStart());
        onMounted(() => this._maybeStart());
        onWillUnmount(() => this._stop());
    }

    get record() {
        return this.props.record;
    }

    _maybeStart() {
        if (this.state.active) {
            return;
        }
        const d = this.record.data;
        const deviceFlow = d.auth_type === "oauth_device_code" && d.device_code;
        const loopbackFlow = d.auth_type === "oauth_external" && d.listening;
        if ((deviceFlow || loopbackFlow) && !d.connected) {
            this.state.active = true;
            this._deadline = Date.now() + MAX_DURATION_MS;
            this._schedule(POLL_INTERVAL_MS);
        }
    }

    _schedule(delay) {
        this._timer = browser.setTimeout(() => this._pollOnce(), delay);
    }

    _stop() {
        if (this._timer) {
            browser.clearTimeout(this._timer);
            this._timer = null;
        }
        this.state.active = false;
    }

    async _pollOnce() {
        if (!this.state.active || !this.record.resId) {
            return;
        }
        let result;
        try {
            result = await this.orm.call("ai.oauth.wizard", "action_poll", [[this.record.resId]]);
        } catch (e) {
            // surface the error (UserError dialog) and stop the loop
            this._stop();
            throw e;
        }
        if (!this.state.active) {
            return;
        }
        if (result && result.type === "ir.actions.act_window_close") {
            this._stop();
            this.notification.add(_t("Connected! Tokens stored."), { type: "success" });
            this.action.doAction(result);
            return;
        }
        // Still pending: refresh the status text, then keep polling until the deadline.
        try {
            await this.record.load();
        } catch {
            this._stop();
            return;
        }
        if (Date.now() > this._deadline) {
            this._stop();
            return;
        }
        this._schedule(POLL_INTERVAL_MS);
    }
}

export const oAuthAutoPoll = { component: OAuthAutoPoll };
registry.category("view_widgets").add("oauth_auto_poll", oAuthAutoPoll);
