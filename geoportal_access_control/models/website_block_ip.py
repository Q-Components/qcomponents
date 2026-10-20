# -*- coding: utf-8 -*-
import ipaddress

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class BlockedIP(models.Model):
    _name = "website.blocked.ip"
    _description = "Blocked Website IP"
    _rec_name = 'ip_address'

    ip_address = fields.Char(string="Ip Address")
    active = fields.Boolean(default=True, string='Active')
    note = fields.Char('Note')
    unblocked = fields.Boolean(
        string="Unblocked",
        help="Enable to ALLOW this IP / CIDR even if another rule blocks it. "
             "It will also never be auto-blocked.")
    auto_blocked = fields.Boolean(string="Auto Blocked", readonly=True)

    @api.constrains('ip_address')
    def _check_ip(self):
        for rec in self:
            if self.search([('ip_address', '=', rec.ip_address), ('id', '!=', rec.id)], limit=1):
                raise ValidationError("This IP address is already blocked.")

    def _get_network(self):
        """Return the ip_network for this rule (single IP => /32 or /128)."""
        self.ensure_one()
        try:
            return ipaddress.ip_network((self.ip_address or "").strip(), strict=False)
        except ValueError:
            return None

    @api.model
    def _get_ip_status(self, ip_obj):
        """'unblocked' if an active 'unblocked' rule matches (always wins),
        'blocked' if an active blocking rule matches, otherwise False."""
        status = False
        for rec in self.search([('active', '=', True)]):
            net = rec._get_network()
            if net is not None and ip_obj in net:
                if rec.unblocked:
                    return 'unblocked'
                status = 'blocked'
        return status

    @api.model
    def _is_ip_covered(self, ip_obj):
        """True if ANY rule (exact IP or CIDR, active, archived or unblocked)
        already contains this IP. Used so auto-block never duplicates."""
        for rec in self.with_context(active_test=False).search([]):
            net = rec._get_network()
            if net is not None and ip_obj in net:
                return True
        return False