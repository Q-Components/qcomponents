# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import api, fields, models
from urllib.parse import urlencode
import requests

_logger = logging.getLogger(__name__)

# The Microsoft Graph endpoint for managing subscriptions (webhooks)
GRAPH_SUBSCRIPTIONS_URL = "https://graph.microsoft.com/v1.0/subscriptions"

# Max lifetime Microsoft allows for a driveItem subscription (~29 days)
SUBSCRIPTION_DAYS = 29

# Microsoft Graph endpoint for drive quota
GRAPH_DRIVE_QUOTA_URL = "https://graph.microsoft.com/v1.0/me/drive?$select=quota"


class OneDriveConfiguration(models.Model):
    _name = "onedrive.configuration"
    _description = "OneDrive Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Name",tracking=True,help="Name of the Instance")
    ms_client_id = fields.Char(string="Client ID",help="Enter the Application client ID generated from the Azure app registration.")
    ms_secret = fields.Char(string="Client Secret",help="Enter the client secret value created in the Azure app registration.")
    ms_redirect_url = fields.Char(string="Redirect URL",help="Microsoft authentication redirect URI", default=lambda self: f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')}/microsoft/auth/callback")
    root_folder_name = fields.Char(string="Root Folder Name",help="Root Folder Name")
    ms_access_token = fields.Char(string="Access Token", copy=False)
    ms_refresh_token = fields.Char(string="Refresh Token", copy=False)
    # ms_tenant_id = fields.Char(string="Tenant ID",help="Enter the Directory (Tenant) ID from the Azure portal.")
    state = fields.Selection([("connecting", "Connecting"),("connected","Connected"),("failed","Failed")],string="State",default="connecting")
    reason = fields.Text(string="Reason")
    auto_delete = fields.Boolean(string="Auto Delete",default=False,help="If enabled, deleting a document  will also delete it from OneDrive.")

    # ── Webhook fields ─────────────────────────────────────────────────────────
    webhook_enabled = fields.Boolean(
        string="Real-Time Sync (Webhook)",
        default=False,
        help="When enabled, Microsoft will notify Odoo the moment any file changes in OneDrive.",
    )
    subscription_ids = fields.One2many(
        "onedrive.subscription",
        "config_id",
        string="Webhook Subscriptions",
    )
    subscription_count = fields.Integer(
        string="Subscriptions",
        compute="_compute_subscription_count",
    )

    # ── Folder Mapping Rules ──────────────────────────────────────────────────
    folder_rule_count = fields.Integer(
        string="Folder Rules",
        compute="_compute_folder_rule_count",
        help="Number of active folder mapping rules for this configuration.",
    )

    # ── Storage Quota (fetched live from Microsoft Graph) ─────────────────────
    quota_total_bytes = fields.Float(
        string="Total Storage (bytes)",
        default=0.0,
        readonly=True,
        help="Total OneDrive storage capacity in bytes.",
    )
    quota_used_bytes = fields.Float(
        string="Used Storage (bytes)",
        default=0.0,
        readonly=True,
        help="Storage currently used in bytes.",
    )
    quota_remaining_bytes = fields.Float(
        string="Remaining Storage (bytes)",
        default=0.0,
        readonly=True,
        help="Remaining storage before reaching the limit, in bytes.",
    )
    quota_deleted_bytes = fields.Float(
        string="Recycle Bin (bytes)",
        default=0.0,
        readonly=True,
        help="Storage consumed by files in the OneDrive recycle bin, in bytes.",
    )
    quota_state = fields.Selection(
        [
            ("normal",   "Normal"),
            ("nearing",  "Nearing Limit"),
            ("critical", "Critical"),
            ("exceeded", "Exceeded"),
            ("unknown",  "Unknown"),
        ],
        string="Storage State",
        default="unknown",
        readonly=True,
    )
    quota_used_gb = fields.Float(
        string="Used (GB)",
        compute="_compute_quota_display",
        store=False,
    )
    quota_total_gb = fields.Float(
        string="Total (GB)",
        compute="_compute_quota_display",
        store=False,
    )
    quota_remaining_gb = fields.Float(
        string="Remaining (GB)",
        compute="_compute_quota_display",
        store=False,
    )
    quota_deleted_gb = fields.Float(
        string="Recycle Bin (GB)",
        compute="_compute_quota_display",
        store=False,
    )
    quota_used_percent = fields.Float(
        string="Used (%)",
        compute="_compute_quota_display",
        store=False,
        help="Percentage of total storage currently used.",
    )
    quota_last_checked = fields.Datetime(
        string="Quota Last Checked",
        readonly=True,
        help="Timestamp of the last successful quota fetch from Microsoft Graph.",
    )
    quota_storage_bar_html = fields.Html(
        string="Storage Bar",
        compute="_compute_quota_storage_bar_html",
        store=False,
        sanitize=False,
        help="Visual HTML progress bar representing OneDrive storage usage.",
    )
    onedrive_root_folder_id = fields.Many2one(
        "documents.document",
        string="Odoo Root Folder",
        help="The Odoo folder that acts as the root container for all OneDrive items.",
    )

    # ── Compute ───────────────────────────────────────────────────────────────
    @api.depends("subscription_ids")
    def _compute_subscription_count(self):
        for rec in self:
            rec.subscription_count = len(rec.subscription_ids)

    @api.depends()
    def _compute_folder_rule_count(self):
        Rule = self.env["onedrive.folder.rule"]
        for rec in self:
            rec.folder_rule_count = Rule.search_count([
                ("onedrive_config_id", "=", rec.id),
                ("active", "=", True),
            ])

    @api.depends("quota_total_bytes", "quota_used_bytes", "quota_remaining_bytes", "quota_deleted_bytes")
    def _compute_quota_display(self):
        """
        Convert raw byte values → human-readable GB figures and usage percentage.
        Non-stored computed fields: recalculate automatically when byte fields change.

        Note: quota_used_gb / quota_total_gb etc. are stored as Float (GB) for the
        Breakdown grid fields. The bar HTML uses a separate smart-unit helper that
        auto-selects MB vs GB based on magnitude, so tiny "used" values like 18 KB
        are never displayed as "0.00 GB".
        """
        GB = 1024 ** 3
        for rec in self:
            # These drive the Breakdown grid — keep GB with enough decimals so
            # small values are still visible (e.g. 0.000018 GB → shown as 0.0000 in grid)
            rec.quota_used_gb      = round(rec.quota_used_bytes      / GB, 6) if rec.quota_used_bytes      else 0.0
            rec.quota_total_gb     = round(rec.quota_total_bytes      / GB, 2) if rec.quota_total_bytes     else 0.0
            rec.quota_remaining_gb = round(rec.quota_remaining_bytes  / GB, 2) if rec.quota_remaining_bytes else 0.0
            rec.quota_deleted_gb   = round(rec.quota_deleted_bytes    / GB, 6) if rec.quota_deleted_bytes   else 0.0
            if rec.quota_total_bytes:
                # Use 4 decimal places so tiny usage like 0.0003% isn't rounded to 0.0%
                rec.quota_used_percent = round((rec.quota_used_bytes / rec.quota_total_bytes) * 100, 4)
            else:
                rec.quota_used_percent = 0.0

    @api.depends("quota_used_bytes", "quota_total_bytes", "quota_deleted_bytes", "quota_state", "quota_used_percent")
    def _compute_quota_storage_bar_html(self):
        """
        Build the visual HTML storage bar rendered in the form view.

        Layout:
          ┌───────────────────────────────────────────┐
          │  [Used ██████████░░░░░░░░] 37.5%          │
          │  37.50 GB used · 62.50 GB free · 100 GB   │
          │  🗑 Recycle Bin: 0.02 GB                   │
          └───────────────────────────────────────────┘

        Color scheme follows the quota state:
          normal   → OneDrive blue  (#0078D4)
          nearing  → amber          (#F59E0B)
          critical → red-orange     (#EF4444)
          exceeded → dark red       (#7F1D1D)
        """
        STATE_COLORS = {
            "normal":   "#0078D4",   # Microsoft OneDrive blue
            "nearing":  "#F59E0B",   # Amber
            "critical": "#EF4444",   # Red
            "exceeded": "#7F1D1D",   # Dark red
            "unknown":  "#9CA3AF",   # Grey
        }
        STATE_BG = {
            "normal":   "#EFF6FF",
            "nearing":  "#FFFBEB",
            "critical": "#FEF2F2",
            "exceeded": "#450A0A",
            "unknown":  "#F9FAFB",
        }

        for rec in self:
            if not rec.quota_total_bytes:
                rec.quota_storage_bar_html = ""
                continue

            pct       = min(rec.quota_used_percent, 100.0)
            state     = rec.quota_state or "unknown"
            bar_color = STATE_COLORS.get(state, STATE_COLORS["unknown"])
            bg_color  = STATE_BG.get(state, STATE_BG["unknown"])

            def _smart_size(byte_val):
                """Auto-select unit: B / KB / MB / GB based on magnitude."""
                if byte_val <= 0:
                    return "0 B"
                KB = 1024
                MB = 1024 ** 2
                GB = 1024 ** 3
                if byte_val < KB:
                    return f"{int(byte_val)} B"
                elif byte_val < MB:
                    return f"{byte_val / KB:.2f} KB"
                elif byte_val < GB:
                    return f"{byte_val / MB:.2f} MB"
                else:
                    return f"{byte_val / GB:.2f} GB"

            used_label      = _smart_size(rec.quota_used_bytes)
            total_label     = _smart_size(rec.quota_total_bytes)
            remaining_label = _smart_size(rec.quota_remaining_bytes)
            deleted_label   = _smart_size(rec.quota_deleted_bytes)

            # Show enough decimal places so tiny usage like 0.0003% is readable
            if pct < 0.01:
                pct_label = f"{pct:.4f}%"
            elif pct < 1.0:
                pct_label = f"{pct:.2f}%"
            else:
                pct_label = f"{pct:.1f}%"

            # Minimum visual bar width of 0.3% so there is always a visible sliver
            bar_pct = max(pct, 0.3) if rec.quota_used_bytes > 0 else 0.0

            # Animated shimmer on the filled bar segment for "live" feel
            html = f"""
<div style="
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: {bg_color};
    border: 1px solid {bar_color}33;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 4px 0 8px 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
">
    <!-- Bar header: label + percentage -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-size:0.82rem; font-weight:600; color:#374151; letter-spacing:0.02em;">
            STORAGE USAGE
        </span>
        <span style="
            font-size:0.95rem;
            font-weight:700;
            color:{bar_color};
            background:{bar_color}18;
            padding:2px 10px;
            border-radius:20px;
        ">{pct_label}</span>
    </div>

    <!-- Progress bar track -->
    <div style="
        background: #E5E7EB;
        border-radius: 999px;
        height: 14px;
        width: 100%;
        overflow: hidden;
        margin-bottom: 10px;
        position: relative;
    ">
        <!-- Filled segment -->
        <div style="
            width: {bar_pct}%;
            height: 100%;
            background: linear-gradient(90deg, {bar_color}CC, {bar_color});
            border-radius: 999px;
            transition: width 0.6s ease;
            position: relative;
            overflow: hidden;
        ">
            <!-- Shimmer overlay for animated effect -->
            <div style="
                position: absolute;
                top: 0; left: -60%;
                width: 60%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent);
                animation: shimmer 2.2s infinite;
            "></div>
        </div>
    </div>

    <!-- Metrics row -->
    <div style="display:flex; gap:20px; flex-wrap:wrap; font-size:0.82rem; color:#6B7280;">
        <span>
            <span style="font-weight:600; color:{bar_color};">{used_label}</span>
            <span style="margin-left:3px;">used</span>
        </span>
        <span>·</span>
        <span>
            <span style="font-weight:600; color:#10B981;">{remaining_label}</span>
            <span style="margin-left:3px;">free</span>
        </span>
        <span>·</span>
        <span>
            <span style="font-weight:600; color:#374151;">{total_label}</span>
            <span style="margin-left:3px;">total</span>
        </span>
    </div>

    <!-- Recycle bin row -->
    <div style="margin-top:8px; font-size:0.79rem; color:#9CA3AF; border-top:1px solid {bar_color}22; padding-top:7px;">
        🗑&nbsp; <strong>{deleted_label}</strong> in recycle bin
        &nbsp;·&nbsp;
        <span style="color:{bar_color}; font-weight:500;">
            {state.replace('_', ' ').title()}
        </span>
    </div>
</div>

<!-- Shimmer keyframes -->
<style>
@keyframes shimmer {{
    0%   {{ left: -60%; }}
    100% {{ left: 130%; }}
}}
</style>
"""
            rec.quota_storage_bar_html = html

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_view_folder_rules(self):
        """Open the folder mapping rules filtered to this configuration."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Folder Mapping Rules",
            "res_model": "onedrive.folder.rule",
            "view_mode": "list,form",
            "domain": [("onedrive_config_id", "=", self.id)],
            "context": {"default_onedrive_config_id": self.id},
        }

    # ──────────────────────────────────────────────────────────────────────────
    # STORAGE QUOTA: FETCH FROM MICROSOFT GRAPH
    # ──────────────────────────────────────────────────────────────────────────
    def action_refresh_storage_quota(self):
        """
        Button action — fetch the latest OneDrive storage quota from Microsoft Graph
        and persist it into the quota_* fields on this record.

        Endpoint:
            GET https://graph.microsoft.com/v1.0/me/drive?$select=quota

        The `quota` object in the response contains:
            total     → total allowed storage in bytes
            used      → bytes currently used (includes recycle bin)
            remaining → bytes left before hitting the limit
            deleted   → bytes sitting in the recycle bin
            state     → 'normal' | 'nearing' | 'critical' | 'exceeded'

        Required scope: Files.Read — already present in this module's OAuth flow.
        No extra Azure permissions or API scopes are needed.
        """
        self.ensure_one()

        # ── Step 1: Make sure we have a fresh, valid token ────────────────────
        # Tokens can expire between sessions; always refresh before calling Graph.
        self.refresh_onedrive_access_token()

        access_token = self.ms_access_token or ""
        # Strip any accidentally persisted "Bearer " prefix
        if access_token.startswith("Bearer "):
            access_token = access_token[len("Bearer "):]

        if not access_token:
            return self.display_notification(
                "No valid access token found. Please reconnect your OneDrive account first.",
                title="Token Missing",
                type="danger",
            )

        # ── Step 2: Call the Graph API ────────────────────────────────────────
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(GRAPH_DRIVE_QUOTA_URL, headers=headers, timeout=15)
        except requests.exceptions.RequestException as e:
            _logger.error("[OneDrive Quota] Network error fetching quota: %s", e)
            return self.display_notification(
                f"Network error while fetching storage info: {e}",
                title="Connection Error",
                type="danger",
            )

        if response.status_code != 200:
            _logger.error(
                "[OneDrive Quota] Graph API returned %s: %s",
                response.status_code, response.text,
            )
            return self.display_notification(
                f"Microsoft Graph returned an error ({response.status_code}). "
                "Please check the server logs for details.",
                title="API Error",
                type="danger",
            )

        # ── Step 3: Parse and persist the quota data ──────────────────────────
        data  = response.json()
        quota = data.get("quota", {})

        if not quota:
            # This can happen with certain OneDrive for Business / SharePoint
            # configurations where quota is not exposed via the /me/drive endpoint.
            _logger.warning(
                "[OneDrive Quota] Config '%s': Graph responded but quota object is empty. "
                "This may be a OneDrive for Business tenant restriction.", self.name
            )
            return self.display_notification(
                "Microsoft Graph responded but returned no quota data. "
                "Some OneDrive for Business configurations restrict quota visibility. "
                "Check with your Microsoft admin.",
                title="No Quota Data",
                type="warning",
            )

        total     = quota.get("total",     0)
        used      = quota.get("used",      0)
        remaining = quota.get("remaining", 0)
        deleted   = quota.get("deleted",   0)
        state     = quota.get("state",     "unknown")

        # Clamp state to our selection values — Graph may return unexpected strings
        valid_states = {"normal", "nearing", "critical", "exceeded"}
        if state not in valid_states:
            _logger.warning(
                "[OneDrive Quota] Unexpected state value '%s' for config '%s'. Defaulting to 'unknown'.",
                state, self.name,
            )
            state = "unknown"

        self.write({
            "quota_total_bytes":     float(total),
            "quota_used_bytes":      float(used),
            "quota_remaining_bytes": float(remaining),
            "quota_deleted_bytes":   float(deleted),
            "quota_state":           state,
            "quota_last_checked":    fields.Datetime.now(),
        })

        _logger.info(
            "[OneDrive Quota] '%s' — Total: %.2f GB | Used: %.2f GB | "
            "Remaining: %.2f GB | Recycle Bin: %.2f GB | State: %s",
            self.name,
            total     / (1024 ** 3),
            used      / (1024 ** 3),
            remaining / (1024 ** 3),
            deleted   / (1024 ** 3),
            state,
        )

        def _fmt(b):
            KB, MB, GB = 1024, 1024**2, 1024**3
            if b < KB:   return f"{int(b)} B"
            if b < MB:   return f"{b/KB:.2f} KB"
            if b < GB:   return f"{b/MB:.2f} MB"
            return f"{b/GB:.2f} GB"

        return self.display_notification(
            f"{_fmt(used)} used of {_fmt(total)} total  •  State: {state.title()}",
            title="Storage Quota Refreshed ✅",
            type="success",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # STORAGE QUOTA: CRON METHOD
    # ──────────────────────────────────────────────────────────────────────────
    @api.model
    def _cron_refresh_all_storage_quotas(self):
        """
        Cron method: Refresh storage quota for every connected OneDrive config.
        Wire this to cron_data.xml (see the separate cron entry in that file).
        Runs silently — errors are logged but never crash the cron.
        """
        configs = self.search([("state", "=", "connected")])
        for config in configs:
            try:
                config.action_refresh_storage_quota()
            except Exception as e:
                _logger.error(
                    "[OneDrive Quota Cron] Failed to refresh quota for config '%s': %s",
                    config.name, e,
                )

    # ──────────────────────────────────────────────────────────────────────────
    # WEBHOOK: SUBSCRIBE
    # ──────────────────────────────────────────────────────────────────────────
    def action_subscribe_webhook(self):
        """
        Register a webhook with Microsoft Graph so that Microsoft calls
        our Odoo URL whenever a file changes in OneDrive.

        What happens here:
          0. Auto-refresh the access token (prevents IDX14100 JWT errors from stale tokens)
          1. Build our public callback URL (e.g., https://myodoo.com/microsoft/webhook/notify)
          2. POST to Microsoft Graph /subscriptions with that URL
          3. Microsoft validates our URL (sends a token, we must echo it back — handled in the controller)
          4. Save the subscription details (subscription_id, expiry, client_state) in Odoo
        """
        self.ensure_one()

        # ── Step 0: Refresh token first ───────────────────────────────────────
        # Personal Microsoft account tokens can expire quickly.
        # Always fetch a fresh one before calling the subscriptions API.
        _logger.info("[OneDrive Webhook] Refreshing access token before subscribing...")
        self.refresh_onedrive_access_token()

        # Re-read the token after refresh
        access_token = self.ms_access_token

        # Safety: strip any accidental "Bearer " prefix stored in the field
        if access_token and access_token.startswith("Bearer "):
            access_token = access_token[len("Bearer "):]

        if not access_token:
            return self.display_notification(
                "Access token is missing. Please reconnect your OneDrive account.", type="danger"
            )

        # NOTE: Personal Microsoft account tokens are OPAQUE (no dots) — this is normal.
        # They work fine for Microsoft Graph calls. We do NOT check for JWT format here.
        _logger.info(
            "[OneDrive Webhook] Token ready. Length: %d | Has dots (JWT): %s",
            len(access_token),
            "." in access_token,
        )

        # ── Step 1: Build the webhook notification URL ────────────────────────
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")

        # Microsoft REQUIRES HTTPS — warn clearly if the URL is not HTTPS
        if not base_url.startswith("https://"):
            return self.display_notification(
                f"Your Odoo base URL '{base_url}' does not use HTTPS. "
                "Microsoft Graph requires a public HTTPS URL for webhook notifications.",
                type="danger",
                sticky=True,
            )

        notify_url = f"{base_url}/microsoft/webhook/notify"
        _logger.info("[OneDrive Webhook] Notification URL: %s", notify_url)

        # ── Step 2: Generate a secret clientState ─────────────────────────────
        import uuid
        client_state = str(uuid.uuid4())

        # ── Step 3: Build and send the subscription request ───────────────────
        expiry = fields.Datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)
        expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

        payload = {
            "changeType": "updated",        # Only supported changeType for driveItem
            "notificationUrl": notify_url,  # Our Odoo webhook endpoint
            "resource": "me/drive/root",    # No leading slash — correct format for Graph subscriptions
            "expirationDateTime": expiry_str,
            "clientState": client_state,
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        _logger.info("[OneDrive Webhook] Sending subscription payload: %s", payload)

        try:
            response = requests.post(GRAPH_SUBSCRIPTIONS_URL, json=payload, headers=headers, timeout=30)
            _logger.info("[OneDrive Webhook] Subscription response status: %s", response.status_code)

            if response.status_code == 201:
                data = response.json()

                # Remove any old subscription record for this config
                self.subscription_ids.unlink()

                # Save the new subscription in Odoo
                self.env["onedrive.subscription"].create({
                    "config_id": self.id,
                    "subscription_id": data.get("id"),
                    "expiration_datetime": expiry,
                    "client_state": client_state,
                    "state": "active",
                })
                self.webhook_enabled = True
                return self.display_notification(
                    "Real-time sync activated! Microsoft will now notify Odoo on every OneDrive change.",
                    title="Webhook Registered ✅",
                    type="success",
                    sticky=True,
                )
            else:
                # Log the full Microsoft error for debugging
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                    error_code = error_data.get("error", {}).get("code", "Unknown")
                    _logger.error(
                        "[OneDrive Webhook] Subscription failed. Code: %s | Message: %s | Full response: %s",
                        error_code, error_msg, response.text,
                    )
                except Exception:
                    error_msg = response.text
                    _logger.error("[OneDrive Webhook] Subscription failed. Response: %s", response.text)

                return self.display_notification(
                    f"Webhook registration failed: {error_msg}", type="danger", sticky=True
                )

        except requests.exceptions.RequestException as e:
            _logger.error("[OneDrive Webhook] Network error during subscription: %s", e)
            return self.display_notification(f"Network error: {e}", type="danger", sticky=True)

    # ──────────────────────────────────────────────────────────────────────────
    # WEBHOOK: UNSUBSCRIBE
    # ──────────────────────────────────────────────────────────────────────────
    def action_unsubscribe_webhook(self):
        """
        Delete the webhook from Microsoft Graph and remove it from Odoo.
        After this, Microsoft will stop sending notifications.
        """
        self.ensure_one()
        sub = self.subscription_ids[:1]  # Get first subscription (there's max one per config)

        if not sub:
            return self.display_notification("No active webhook found.", type="warning")

        headers = {"Authorization": f"Bearer {self.ms_access_token}"}
        try:
            url = f"{GRAPH_SUBSCRIPTIONS_URL}/{sub.subscription_id}"
            response = requests.delete(url, headers=headers, timeout=30)
            # 204 = success, 404 = already gone — both are OK
            if response.status_code in (204, 404):
                sub.unlink()
                self.webhook_enabled = False
                return self.display_notification("Webhook removed. Real-time sync disabled.", type="info")
            else:
                return self.display_notification(f"Could not remove webhook: {response.text}", type="warning")
        except requests.exceptions.RequestException as e:
            return self.display_notification(f"Network error: {e}", type="danger")

    # ──────────────────────────────────────────────────────────────────────────
    # WEBHOOK: AUTO-RENEW (called by Cron Job)
    # ──────────────────────────────────────────────────────────────────────────
    @api.model
    def _renew_webhook_subscriptions(self):
        """
        Cron job method: Runs every 7 days.
        Finds all subscriptions expiring within 3 days and renews them.
        This prevents real-time sync from silently stopping.
        """
        renew_before = fields.Datetime.now() + timedelta(days=3)

        # Find subscriptions that expire within the next 3 days
        expiring_subs = self.env["onedrive.subscription"].search([
            ("state", "=", "active"),
            ("expiration_datetime", "<=", renew_before),
        ])

        for sub in expiring_subs:
            config = sub.config_id
            if not config.ms_access_token:
                _logger.warning("OneDrive renewal skipped for config %s — no access token.", config.name)
                continue

            new_expiry = fields.Datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)
            new_expiry_str = new_expiry.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")

            headers = {
                "Authorization": f"Bearer {config.ms_access_token}",
                "Content-Type": "application/json",
            }
            payload = {"expirationDateTime": new_expiry_str}

            try:
                url = f"{GRAPH_SUBSCRIPTIONS_URL}/{sub.subscription_id}"
                response = requests.patch(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    sub.expiration_datetime = new_expiry
                    _logger.info("Renewed OneDrive webhook for config '%s'.", config.name)
                else:
                    sub.state = "failed"
                    _logger.error("Renewal failed for config '%s': %s", config.name, response.text)
            except requests.exceptions.RequestException as e:
                sub.state = "failed"
                _logger.error("Network error during renewal for config '%s': %s", config.name, e)

    # ──────────────────────────────────────────────────────────────────────────
    # EXISTING METHODS (unchanged)
    # ──────────────────────────────────────────────────────────────────────────

    def action_connect_onedrive(self):
        self.ensure_one()
        params = {
            "client_id": self.ms_client_id,
            "response_type": "code",
            "redirect_uri": self.ms_redirect_url,
            "response_mode": "query",
            "scope": "offline_access Files.ReadWrite.All User.Read",
            "state": self.id,
        }

        auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def reconnect_with_onedrive(self):
        self.state = 'connecting'
        self.ms_access_token = ''
        self.ms_refresh_token = ''
        self.reason = ''

    def refresh_onedrive_access_token(self):
        onedrive_configs = self if self else self.env['onedrive.configuration'].sudo().search(
            [('state', '=', 'connected')]
        )
        for rec in onedrive_configs:

            token_data = {
                "client_id": rec.ms_client_id,
                "client_secret": rec.ms_secret,
                "refresh_token": rec.ms_refresh_token,
                "grant_type": "refresh_token",
                "scope": "offline_access Files.ReadWrite.All User.Read",
            }
            MICROSOFT_TOKEN_URL = f"https://login.microsoftonline.com/common/oauth2/v2.0/token"
            try:
                response = requests.post(MICROSOFT_TOKEN_URL, data=token_data, timeout=30)

                if response.status_code == 200:
                    tokens = response.json()
                    rec.write({
                        "ms_access_token": tokens.get("access_token"),
                        "ms_refresh_token": tokens.get("refresh_token"),
                        "reason": "Successfully connected with OneDrive"
                    })
                else:
                    rec.write({"reason": f"Token refresh failed: {response.text}"})
            except requests.exceptions.RequestException as e:
                rec.write({"reason": str(e)})

    def display_notification(self, message, title="Notification", type="success", sticky=False, next_action=None):
        """
        Reusable method for display notifications.
        :param message: The body of the notification.
        :param title: The title of the notification.
        :param type: 'info', 'success', 'warning', or 'danger'
        :param sticky: Boolean to make the notification stay until dismissed.
        :param next_action: Optional next action dict, e.g., {'type': 'ir.actions.act_window_close'}
        :return: Client action dictionary
        """
        params = {
            "title": title,
            "message": message,
            "type": type,
            "sticky": sticky,
        }
        if next_action:
            params["next"] = next_action

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": params,
        }
