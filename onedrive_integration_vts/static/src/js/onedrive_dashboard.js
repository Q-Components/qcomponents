// ============================================================================
// OneDrive Dashboard — Main Widget
// Fetches KPI data from Python and renders the full dashboard UI.
// Uses OWL (Odoo Web Library) — same pattern as Odoo 17/18/19 dashboards.
// ============================================================================

/** @odoo-module **/

import { registry }      from "@web/core/registry";
import { useService }    from "@web/core/utils/hooks";
import { Component, onMounted, useState } from "@odoo/owl";

// ─── Color helpers ───────────────────────────────────────────────────────────
const STATUS_COLOR = {
    success: "#16A34A",
    failed:  "#DC2626",
    skipped: "#D97706",
};
const OP_ICON = {
    upload:   "fa-cloud-upload",
    download: "fa-cloud-download",
    delete:   "fa-trash",
    webhook:  "fa-bolt",
    folder:   "fa-folder",
    update:   "fa-sync",
    restore:  "fa-history",
};
const OP_COLOR = {
    upload:   "#2563EB",
    download: "#15803D",
    delete:   "#DC2626",
    webhook:  "#7C3AED",
    folder:   "#D97706",
    update:   "#2563EB",
    restore:  "#0891B2",
};
const QUOTA_COLOR = {
    normal:   "#16A34A",
    nearing:  "#D97706",
    critical: "#DC2626",
    exceeded: "#991B1B",
    unknown:  "#94A3B8",
};

// ─── Dashboard Component ──────────────────────────────────────────────────────
export class OneDriveDashboard extends Component {
    static template = "onedrive_integration_vts.DashboardTemplate";
    static props    = ["*"];

    setup() {
        // Odoo 17+ uses 'orm' service — 'rpc' no longer exists as a service
        this.orm    = useService("orm");
        this.action = useService("action");
        this.state  = useState({
            data:    null,
            loading: true,
            error:   null,
        });

        onMounted(() => this._loadData());
    }

    async _loadData() {
        try {
            // orm.call(model, method, args=[], kwargs={}) — Odoo 17+/19 standard
            const data = await this.orm.call(
                "onedrive.dashboard",
                "get_dashboard_data",
                [],
                {}
            );
            this.state.data    = data;
            this.state.loading = false;
        } catch (e) {
            this.state.error   = "Failed to load dashboard data.";
            this.state.loading = false;
        }
    }

    // ── Helpers exposed to template ──────────────────────────────────────────
    get statusColor()  { return STATUS_COLOR; }
    get opIcon()       { return OP_ICON; }
    get opColor()      { return OP_COLOR; }
    get quotaColor()   { return QUOTA_COLOR; }

    openHistory() {
        this.action.doAction(this.state.data.action_history);
    }

    openHistoryToday() {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      "Today's Sync History",
            res_model: "onedrive.sync.history",
            view_mode: "list,form",
            domain:    [["create_date", ">=", this.state.data.today_start_str]],
            views:     [[false, "list"], [false, "form"]],
        });
    }

    openDocuments() {
        this.action.doAction("documents.document_action");
    }

    openConfig() {
        this.action.doAction(this.state.data.action_config);
    }

    openHistoryFiltered(status) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            name:      "Sync History",
            res_model: "onedrive.sync.history",
            view_mode: "list,form",
            domain:    [["status", "=", status]],
            views:     [[false, "list"], [false, "form"]],
        });
    }

    openConfigRecord(id) {
        this.action.doAction({
            type:      "ir.actions.act_window",
            res_model: "onedrive.configuration",
            res_id:    id,
            view_mode: "form",
            views:     [[false, "form"]],
        });
    }
}

// Register as a client action
registry.category("actions").add("onedrive_dashboard_action", OneDriveDashboard);
