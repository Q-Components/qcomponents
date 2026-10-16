import requests
import logging
import threading
from odoo import http, fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class OneDriveOAuthController(http.Controller):

    @http.route("/microsoft/auth/callback", type="http", auth="user", website=True)
    def onedrive_auth_callback(self,**kwargs):
        code = kwargs.get("code")
        state = kwargs.get("state")
        if not code or not state:
            return "Invalid  callback"
        onedrive_config = None
        try:
            onedrive_config = request.env["onedrive.configuration"].sudo().browse(int(state))
            if not onedrive_config.exists():
                raise ValueError(f"OneDrive connection ID {state} not found")

            token_data = {
                "client_id": onedrive_config.ms_client_id,
                "client_secret": onedrive_config.ms_secret,
                "code": code,
                "redirect_uri": onedrive_config.ms_redirect_url,
                "grant_type": "authorization_code",
            }
            MICROSOFT_TOKEN_URL = f"https://login.microsoftonline.com/common/oauth2/v2.0/token"

            response = requests.post(MICROSOFT_TOKEN_URL, data=token_data, timeout=30)
            if response.status_code != 200:
                raise ValueError(f"Token exchange failed: {response.text}")

            tokens = response.json()
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            if not access_token or not refresh_token:
                raise ValueError(f"Token response invalid: {tokens}")

            onedrive_config.write({
                "ms_access_token": tokens["access_token"],
                "ms_refresh_token": tokens.get("refresh_token"),
                "state": "connected",
                "reason":"Successfully connected with OneDrive"
            })
        except Exception as e:
            onedrive_config.sudo().write({
                "state": "failed",
                "reason": str(e)
            })
            return request.redirect(f"/web#id={onedrive_config.id}&model=onedrive.configuration&view_type=form")

        return request.redirect(f"/web#id={onedrive_config.id}&model=onedrive.configuration&view_type=form")

    # ── NEW: Microsoft Graph Webhook Endpoint ─────────────────────────────────
    @http.route(
        "/microsoft/webhook/notify",
        type="http",
        auth="public",       # Must be public — Microsoft doesn't send an Odoo session token
        methods=["GET", "POST"],
        csrf=False,          # CSRF protection must be off for external POST calls
        save_session=False,
    )
    def onedrive_webhook_notify(self, **kwargs):
        """
        This is the URL that Microsoft Graph calls when something changes in OneDrive.

        Two cases:
        ─────────
        GET  → Validation handshake (called once when we register the webhook)
               Microsoft sends ?validationToken=abc123
               We must echo it back as plain text with 200 OK

        POST → Change notification (called every time a file changes)
               Body contains subscription info + clientState
               We verify it, respond 202 immediately, then sync in background
        """

        # ── CASE 1: Validation Handshake (GET request) ────────────────────────
        validation_token = kwargs.get("validationToken")
        if validation_token:
            _logger.info("[OneDrive Webhook] Validation handshake received.")
            # Echo the token back as plain text — this proves our URL is valid
            return Response(
                validation_token,
                status=200,
                content_type="text/plain",
            )

        # ── CASE 2: Change Notification (POST request) ────────────────────────
        try:
            body = request.get_json_data()
            notifications = body.get("value", [])
        except Exception:
            _logger.warning("[OneDrive Webhook] Could not parse notification body.")
            return Response(status=400)

        # ────────────────────────────────────────────────────────────────────────
        # IMPORTANT: We MUST respond within 3 seconds or Microsoft retries.
        # So we respond with 202 Accepted first, then run the sync in the background.
        # ────────────────────────────────────────────────────────────────────────
        for notification in notifications:
            client_state = notification.get("clientState")
            subscription_id = notification.get("subscriptionId")

            # Find the matching subscription record in Odoo
            subscription = request.env["onedrive.subscription"].sudo().search(
                [("subscription_id", "=", subscription_id)], limit=1
            )

            if not subscription:
                _logger.warning("[OneDrive Webhook] Unknown subscription ID: %s", subscription_id)
                continue

            # Security check: verify the clientState matches what we stored
            if subscription.client_state != client_state:
                _logger.warning("[OneDrive Webhook] clientState mismatch! Ignoring notification.")
                continue

            config = subscription.config_id

            # Run the delta sync in a background thread so we respond quickly
            thread = threading.Thread(
                target=self._run_delta_sync_in_background,
                args=(config.id, request.env.cr.dbname),
                daemon=True,
            )
            thread.start()

        # Reply immediately with 202 Accepted
        return Response(status=202)

    def _run_delta_sync_in_background(self, config_id, dbname):
        """
        Run the delta sync in a separate thread.
        We need a new database cursor because the original request's cursor
        will be closed by the time this thread runs.
        """
        try:
            # Open a new Odoo environment with a fresh DB connection
            from odoo.modules.registry import Registry
            from odoo import api, SUPERUSER_ID
            
            reg = Registry(dbname)
            with reg.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                config = env["onedrive.configuration"].browse(config_id)
                if config.exists():
                    env["documents.document"]._sync_delta_changes(config)
        except Exception as e:
            _logger.error("[OneDrive Webhook] Background delta sync thread failed: %s", e)
