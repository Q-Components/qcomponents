from odoo import _, api, fields, models
from odoo.exceptions import UserError, AccessError
import logging

_logger = logging.getLogger(__name__)
import smtplib


class ResUser(models.Model):
    _inherit = ['res.users']

    smtp_authentication = fields.Selection(selection_add=[('outlook', 'Outlook OAuth Authentication')])
    outgoing_mail_id = fields.Many2one('ir.mail_server', string='User')
    microsoft_outlook_refresh_token_outgoing = fields.Char(string="microsoft_outlook_refresh_token",
                                                           compute="_compute_microsoft_outlook_refresh_token_outgoing")
    microsoft_outlook_refresh_token_incoming = fields.Char(string="microsoft_outlook_refresh_token_incoming",
                                                           compute="_compute_microsoft_outlook_refresh_token_incoming")
    incoming_mail_id = fields.Many2one('fetchmail.server', string='Incoming User')
    provider_id = fields.Many2one('mail.server', string="Provider")
    is_microsoft_outlook_configured = fields.Boolean('Is Outlook Credential Configured',
                                                     compute='_compute_is_microsoft_outlook_configured')

    def _compute_is_microsoft_outlook_configured(self):
        Config = self.env['ir.config_parameter'].sudo()
        microsoft_outlook_client_id = Config.get_param('microsoft_outlook_client_id')
        microsoft_outlook_client_secret = Config.get_param('microsoft_outlook_client_secret')
        self.is_microsoft_outlook_configured = microsoft_outlook_client_id and microsoft_outlook_client_secret

    @api.depends("outgoing_mail_id")
    def _compute_microsoft_outlook_refresh_token_outgoing(self):
        for record in self:
            if record.outgoing_mail_id.id != False:
                record.microsoft_outlook_refresh_token_outgoing = record.outgoing_mail_id.sudo().microsoft_outlook_refresh_token
            else:
                record.microsoft_outlook_refresh_token_outgoing = False

    @api.depends("incoming_mail_id")
    def _compute_microsoft_outlook_refresh_token_incoming(self):
        for record in self:
            if record.incoming_mail_id.id != False:
                record.microsoft_outlook_refresh_token_incoming = record.incoming_mail_id.sudo().microsoft_outlook_refresh_token
            else:
                record.microsoft_outlook_refresh_token_incoming = False

    def test_smtp_connection(self):
        if self.outgoing_mail_id:
            self.outgoing_mail_id.sudo().test_smtp_connection()
        if self.incoming_mail_id:
            self.incoming_mail_id.sudo().button_confirm_login()
            message = _("Connection Test Successful!")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }

    def open_microsoft_outlook_uri_outgoing(self):
        self.ensure_one()

        if not self.is_microsoft_outlook_configured:
            raise UserError(_('Please configure your Outlook credentials.'))

        if self.outgoing_mail_id.id == False:
            self.sudo().set_mail_server()
            self.outgoing_mail_id = self.env['ir.mail_server'].sudo().search([('user_id', '=', self.id)])

        return {
            'type': 'ir.actions.act_url',
            'url': self.outgoing_mail_id.microsoft_outlook_uri,
        }

    def open_microsoft_outlook_uri_incoming(self):
        self.ensure_one()
        if not self.is_microsoft_outlook_configured:
            raise UserError(_('Please configure your Outlook credentials.'))

        if self.incoming_mail_id.id == False:
            self.sudo().set_mail_server()
            self.incoming_mail_id = self.env['fetchmail.server'].sudo().search([('user_id', '=', self.id)])

        return {
            'type': 'ir.actions.act_url',
            'url': self.incoming_mail_id.sudo().microsoft_outlook_uri,
        }

    def set_mail_server(self):
        current_user = self.env['ir.mail_server'].sudo().search([('user_id', '=', self.id)])

        if current_user:
            self.outgoing_mail_id = current_user.id
            dict = {
                'smtp_user': self.email,
                'from_filter': self.email,
                'name': self.env.user.name,
                'user_id': self.id,
                'mail_server_id': self.provider_id.id,
                'smtp_authentication': self.smtp_authentication
            }
            self.outgoing_mail_id.sudo().write(dict)
        else:
            dict = {
                'smtp_user': self.email,
                'from_filter': self.email,
                'name': self.env.user.name,
                'user_id': self.id,
                'mail_server_id': self.provider_id.id,
                'smtp_authentication': self.smtp_authentication

            }
            self.env['ir.mail_server'].sudo().with_context(default_smtp_encryption=self.provider_id.smtp_encryption,
                                                           default_smtp_port=self.provider_id.smtp_port).create(dict)
        # mail.server
        current_incoming_user = self.env['fetchmail.server'].search([('user_id', '=', self.id)])
        if current_incoming_user:
            self.incoming_mail_id = current_incoming_user.id
            incomingdict = {
                'user': self.email,
                'name': self.name,
                'user_id': self.id,
                'mail_server_id': self.provider_id.id,

            }
            self.incoming_mail_id.sudo().write(incomingdict)
        else:
            incomingdict = {
                'user': self.email,
                'name': self.name,
                'user_id': self.id,
                'mail_server_id': self.provider_id.id,
            }
            self.env['fetchmail.server'].sudo().with_context(default_type=self.provider_id.type).create(incomingdict)
        return True

    @api.model
    def create(self, vals):
        res = super(ResUser, self).create(vals)
        res_config = self.env['res.config.settings'].sudo().get_values()
        if res_config.get('is_auto_generate_mail_server'):
            outgoingdict = {
                'smtp_user': res.email,
                'name': res.name,
                'user_id': res.id,
                'mail_server_id': self.provider_id.id,
                'smtp_authentication': self.smtp_authentication

            }
            self.env['ir.mail_server'].create(outgoingdict)
            incomingdict = {
                'user': res.email,
                'name': res.name,
                'user_id': res.id,
                'mail_server_id': self.provider_id.id,

            }
            self.env['fetchmail.server'].create(incomingdict)
        return res

    def write(self, vals):
        if self._context.get('preference_user') and not self._context.get('is_write_preference'):
            return super(ResUser, self).sudo().with_context(is_write_preference=1).write(vals)
        else:
            return super(ResUser, self).write(vals)
