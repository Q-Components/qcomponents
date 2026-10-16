# -*- coding: utf-8 -*-
"""
OneDrive Webhook Subscription Model
=====================================
This model stores ONE subscription record per OneDrive configuration.
A "subscription" is just the registered webhook with Microsoft Graph API.
Microsoft will call our Odoo URL every time something changes in OneDrive.

Key fields:
- subscription_id   : Microsoft's ID for this webhook registration
- delta_link        : The token used to fetch ONLY what changed since last sync
- expiration_datetime: When Microsoft will stop sending us notifications (max ~29 days)
- client_state      : A secret string to verify notifications are really from Microsoft
"""
import uuid
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class OneDriveSubscription(models.Model):
    _name = "onedrive.subscription"
    _description = "OneDrive Webhook Subscription"

    # ── Relation ──────────────────────────────────────────────────────────────
    config_id = fields.Many2one(
        "onedrive.configuration",
        string="OneDrive Config",
        required=True,
        ondelete="cascade",  # Delete subscription record when config is deleted
    )

    # ── Microsoft Graph fields ─────────────────────────────────────────────────
    subscription_id = fields.Char(
        string="Subscription ID",
        help="The ID returned by Microsoft Graph when we registered the webhook.",
        readonly=True,
    )

    delta_link = fields.Char(
        string="Delta Link",
        help="The URL returned by Microsoft after each delta sync. "
             "We use this next time to fetch ONLY the files that changed.",
        copy=False,
    )

    expiration_datetime = fields.Datetime(
        string="Expires On",
        help="When Microsoft will stop sending webhook notifications. "
             "A cron job renews this automatically before it expires.",
        readonly=True,
    )

    client_state = fields.Char(
        string="Client State (Secret)",
        help="A secret string we send to Microsoft when registering. "
             "Microsoft includes it in every notification so we can verify it's genuine.",
        default=lambda self: str(uuid.uuid4()),  # Random UUID per subscription
        copy=False,
    )

    state = fields.Selection(
        [
            ("active", "Active"),
            ("expired", "Expired"),
            ("failed", "Failed"),
        ],
        string="State",
        default="active",
    )

    last_sync = fields.Datetime(
        string="Last Delta Sync",
        help="The last time we successfully ran a delta-sync after receiving a webhook ping.",
        readonly=True,
    )

    # ──────────────────────────────────────────────────────────────────────────
    @api.constrains('config_id')
    def _check_unique_config_id(self):
        for record in self:
            if record.config_id:
                count = self.search_count([("config_id", "=", record.config_id.id)])
                if count > 1:
                    raise ValidationError("Each OneDrive configuration can have only one active subscription.")
