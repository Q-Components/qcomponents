# -*- coding: utf-8 -*-
"""
OneDrive Integration — Dashboard Model
=======================================
Provides all KPI data consumed by the OneDrive Dashboard client action.
All statistics are computed on demand from existing models — no new storage.
"""
from odoo import api, fields, models
from datetime import timedelta


class OneDriveDashboard(models.AbstractModel):
    """
    Abstract model that acts as a data-service layer for the dashboard.
    All methods return plain Python dicts / lists that the QWeb template
    (embedded in the ir.actions.client record) can render directly via
    the 'onedrive_dashboard' client-action tag.
    """
    _name = "onedrive.dashboard"
    _description = "OneDrive Dashboard Data Service"

    @api.model
    def get_dashboard_data(self):
        """
        Central method called by the dashboard JS widget.
        Returns a single dict with every KPI needed to render the page.
        """
        History = self.env["onedrive.sync.history"].sudo()
        Config  = self.env["onedrive.configuration"].sudo()
        Doc     = self.env["documents.document"].sudo()

        # ── Connection KPIs ──────────────────────────────────────────────────
        all_configs       = Config.search([])
        connected_configs = all_configs.filtered(lambda c: c.state == "connected")
        webhook_active    = connected_configs.filtered(lambda c: c.webhook_enabled)

        # ── Sync History KPIs ────────────────────────────────────────────────
        total_logs   = History.search_count([])
        success_logs = History.search_count([("status", "=", "success")])
        failed_logs  = History.search_count([("status", "=", "failed")])
        skipped_logs = History.search_count([("status", "=", "skipped")])

        # Success rate (avoid division by zero)
        success_rate = round((success_logs / total_logs * 100), 1) if total_logs else 0.0

        # ── Operation Breakdown ───────────────────────────────────────────────
        ops = {}
        for op_key, op_label in [
            ("upload",   "Uploads"),
            ("download", "Imports"),
            ("delete",   "Deletes"),
            ("webhook",  "Webhooks"),
            ("folder",   "Folders"),
            ("update",   "Updates in OneDrive from Odoo"),
            ("restore",  "Restores"),
        ]:
            ops[op_key] = {
                "label":   op_label,
                "total":   History.search_count([("operation", "=", op_key)]),
                "success": History.search_count([("operation", "=", op_key), ("status", "=", "success")]),
                "failed":  History.search_count([("operation", "=", op_key), ("status", "=", "failed")]),
            }

        # ── Recent Activity (last 10 logs) ───────────────────────────────────
        recent = History.search([], limit=10, order="create_date desc")
        recent_data = []
        for r in recent:
            recent_data.append({
                "id":        r.id,
                "date":      r.create_date.strftime("%d %b, %H:%M") if r.create_date else "",
                "operation": r.operation,
                "status":    r.status,
                "file_name": r.file_name or "—",
                "config":    r.config_id.name if r.config_id else "—",
                "message":   (r.message or "")[:120],
            })

        # ── Document KPIs ────────────────────────────────────────────────────
        onedrive_docs   = Doc.with_context(active_test=False).search_count([("onedrive_id", "!=", False)])
        archived_docs   = Doc.with_context(active_test=False).search_count([
            ("onedrive_id", "!=", False), ("active", "=", False)
        ])
        active_docs = onedrive_docs - archived_docs

        # ── Storage across all connected configs ──────────────────────────────
        total_used_bytes      = sum(connected_configs.mapped("quota_used_bytes"))
        total_storage_bytes   = sum(connected_configs.mapped("quota_total_bytes"))
        total_deleted_bytes   = sum(connected_configs.mapped("quota_deleted_bytes"))
        storage_pct           = round((total_used_bytes / total_storage_bytes * 100), 1) if total_storage_bytes else 0.0

        def _fmt_bytes(b):
            if b <= 0:       return "0 B"
            KB = 1024; MB = 1024**2; GB = 1024**3
            if b < KB:       return f"{int(b)} B"
            if b < MB:       return f"{b/KB:.2f} KB"
            if b < GB:       return f"{b/MB:.2f} MB"
            return f"{b/GB:.2f} GB"

        # ── Today's activity ─────────────────────────────────────────────────
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_success = History.search_count([("create_date", ">=", today_start), ("status", "=", "success")])
        today_failed  = History.search_count([("create_date", ">=", today_start), ("status", "=", "failed")])

        # ── Config list for the connections panel ────────────────────────────
        configs_data = []
        for cfg in all_configs:
            sub = cfg.subscription_ids[:1]
            configs_data.append({
                "id":             cfg.id,
                "name":           cfg.name or "Unnamed",
                "state":          cfg.state,
                "webhook":        cfg.webhook_enabled,
                "quota_used":     _fmt_bytes(cfg.quota_used_bytes),
                "quota_total":    _fmt_bytes(cfg.quota_total_bytes),
                "quota_pct":      round((cfg.quota_used_bytes / cfg.quota_total_bytes * 100), 1) if cfg.quota_total_bytes else 0,
                "quota_state":    cfg.quota_state or "unknown",
                "last_sync":      sub.last_sync.strftime("%d %b %Y, %H:%M") if sub and sub.last_sync else "Never",
                "sub_expires":    sub.expiration_datetime.strftime("%d %b %Y") if sub and sub.expiration_datetime else "—",
            })

        return {
            # Connections
            "total_configs":     len(all_configs),
            "connected_configs": len(connected_configs),
            "webhook_active":    len(webhook_active),

            # Sync history totals
            "total_logs":    total_logs,
            "success_logs":  success_logs,
            "failed_logs":   failed_logs,
            "skipped_logs":  skipped_logs,
            "success_rate":  success_rate,

            # Today
            "today_success": today_success,
            "today_failed":  today_failed,
            "today_start_str": today_start.strftime("%Y-%m-%d %H:%M:%S"),

            # Operations breakdown
            "ops": ops,

            # Documents
            "onedrive_docs": onedrive_docs,
            "active_docs":   active_docs,
            "archived_docs": archived_docs,

            # Storage (aggregated)
            "total_used_bytes":    _fmt_bytes(total_used_bytes),
            "total_storage_bytes": _fmt_bytes(total_storage_bytes),
            "total_deleted_bytes": _fmt_bytes(total_deleted_bytes),
            "storage_pct":         storage_pct,

            # Individual configs
            "configs": configs_data,

            # Recent activity feed
            "recent": recent_data,

            # Action IDs for quick-links (looked up by XML ID)
            "action_history":  self.env.ref("onedrive_integration_vts.action_onedrive_sync_history").id,
            "action_config":   self.env.ref("onedrive_integration_vts.action_onedrive_connect").id,
        }
