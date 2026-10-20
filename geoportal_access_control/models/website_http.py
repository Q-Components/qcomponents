import json
import logging
import ipaddress
import re

from odoo import models
from odoo.http import request
from werkzeug.exceptions import Forbidden

_logger = logging.getLogger(__name__)

PARAM = "geoportal_access_control."

# Never touched by this module at all
SKIP_PREFIXES = ("/get_user_location", "/websocket", "/longpolling", "/static")
# Under /web but public website content: these ARE blockable / monitorable
PUBLIC_WEB_PREFIXES = ("/web/image", "/web/content")
# Language prefix such as /en, /fr, /pt_BR
LANG_RE = re.compile(r"^/[a-z]{2,3}(?:_[A-Za-z0-9]+)?(?=/|$)")


class Http(models.AbstractModel):
    _inherit = "ir.http"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _geoportal_path_is_monitored(cls, path):
        """True if monitoring is enabled and path matches a configured URL."""
        icp = request.env["ir.config_parameter"].sudo()
        if icp.get_param(PARAM + "ip_monitor_enabled") != "True":
            return False

        raw = icp.get_param(PARAM + "ip_monitor_url_patterns") or ""
        patterns = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if not line.startswith("/"):
                line = "/" + line
            patterns.append(line)
        if not patterns:
            return False

        candidates = [path]
        match = LANG_RE.match(path)
        if match:
            candidates.append(path[match.end():] or "/")

        return any(c.startswith(p) for c in candidates for p in patterns)

    @classmethod
    def _geoportal_check_country(cls):
        """Raise Forbidden if the visitor's country is blocked."""
        country_code = None
        country_name = None
        try:
            if getattr(request, "geoip", None):
                country_code = request.geoip.country_code
                country_name = request.geoip.country_name
        except Exception as e:
            _logger.debug("GeoIP lookup failed: %s", e)

        if not country_code:
            return

        icp = request.env["ir.config_parameter"].sudo()
        blocked_ids = json.loads(icp.get_param(PARAM + "not_allowed_country_ids", "[]") or "[]")
        if not blocked_ids:
            return

        blocked_codes = request.env["res.country"].sudo().browse(blocked_ids).mapped("code")
        if country_code in blocked_codes:
            _logger.warning("Blocked country access: %s (%s)", country_name, country_code)
            msg = icp.get_param(PARAM + "custom_msg", "Access denied from your country.")
            raise Forbidden(msg)

    @classmethod
    def _geoportal_log_activity(cls, ip_obj, path):
        """Store one activity row. Must never break the website."""
        # if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
        #     return
        try:
            if request.env.user._is_internal():
                return
            user_agent = (request.httprequest.headers.get("User-Agent") or "")[:255]
            with request.env.cr.savepoint():
                request.env["website.ip.activity"].sudo().create({
                    "ip_address": str(ip_obj),
                    "path": path[:255],
                    "user_agent": user_agent,
                })
        except Exception:
            _logger.exception("GeoPortal: could not log IP activity")

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    @classmethod
    def _dispatch(cls, endpoint):
        if not request or not request.httprequest:
            return super()._dispatch(endpoint)

        path = request.httprequest.path or ""

        if path.startswith(SKIP_PREFIXES):
            return super()._dispatch(endpoint)

        is_backend = (path == "/web" or path.startswith("/web/")) \
            and not path.startswith(PUBLIC_WEB_PREFIXES)
        monitored = cls._geoportal_path_is_monitored(path)

        # Backend pages are never blocked; only log them if explicitly monitored
        if is_backend and not monitored:
            return super()._dispatch(endpoint)

        # With proxy_mode = True in odoo.conf, remote_addr is the real client IP
        try:
            ip_obj = ipaddress.ip_address(request.httprequest.remote_addr)
        except (ValueError, TypeError):
            return super()._dispatch(endpoint)

        if not is_backend:
            cls._geoportal_check_country()

        status = request.env["website.blocked.ip"].sudo()._get_ip_status(ip_obj)

        if status == "blocked" and not is_backend:
            _logger.warning("Blocked IP access: %s", ip_obj)
            raise Forbidden("Access denied.")

        # Log only IPs that are neither blocked nor explicitly unblocked
        if status is False and monitored:
            cls._geoportal_log_activity(ip_obj, path)

        return super()._dispatch(endpoint)