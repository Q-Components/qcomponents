# -*- coding: utf-8 -*-
import ipaddress
import logging
import socket
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

PARAM = "geoportal_access_control."
# Reverse-DNS suffixes of genuine Google crawlers
CRAWLER_DOMAINS = (".googlebot.com", ".google.com")


class WebsiteIpActivity(models.Model):
    _name = "website.ip.activity"
    _description = "Website IP Activity"
    _order = "request_date desc, id desc"

    ip_address = fields.Char(required=True, index=True)
    request_date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    path = fields.Char()
    user_agent = fields.Char()

    @api.model
    def _get_int_param(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(PARAM + key)
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default

    @api.model
    def _is_verified_crawler(self, ip):
        """Reverse DNS must end with a Google domain AND forward DNS must
        resolve back to the same IP (the method Google documents)."""
        try:
            ip_obj = ipaddress.ip_address(ip)
            host = socket.gethostbyaddr(ip)[0].lower()
            if not host.endswith(CRAWLER_DOMAINS):
                return False
            infos = socket.getaddrinfo(host, None)
            return any(ipaddress.ip_address(i[4][0]) == ip_obj for i in infos)
        except (OSError, ValueError):
            return False

    @api.model
    def _cron_check_and_block(self):
        icp = self.env['ir.config_parameter'].sudo()
        window = self._get_int_param('ip_monitor_window_minutes', 30)
        threshold = self._get_int_param('ip_monitor_max_requests', 100)
        cr = self.env.cr

        if icp.get_param(PARAM + "ip_monitor_enabled") == "True":
            # 1. IPs that reached the threshold since the last run
            cr.execute("""
                SELECT ip_address, COUNT(*)
                  FROM website_ip_activity
                 GROUP BY ip_address
                HAVING COUNT(*) >= %s
            """, (threshold,))
            rows = cr.fetchall()

            Blocked = self.env['website.blocked.ip'].sudo()
            for ip, count in rows:
                try:
                    ip_obj = ipaddress.ip_address(ip)
                except ValueError:
                    continue
                if Blocked._is_ip_covered(ip_obj):      # exact IP or CIDR already exists
                    continue
                if self._is_verified_crawler(ip):       # real Googlebot
                    continue
                Blocked.create({
                    'ip_address': ip,
                    'note': "Auto-blocked: %s requests in %s minutes" % (count, window),
                    'auto_blocked': True,
                })
                _logger.warning("GeoPortal auto-blocked %s (%s requests / %s min)", ip, count, window)

        # 2. Delete ALL activity rows after every cron run
        cr.execute("DELETE FROM website_ip_activity")
        self.invalidate_model()