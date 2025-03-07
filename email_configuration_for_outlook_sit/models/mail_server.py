from odoo import _, api, fields, models


class MailServer(models.Model):
    _inherit = 'mail.server'

    type = fields.Selection(selection_add=[('outlook', 'Outlook OAuth Authentication'), ]
                            , index=True, default='pop')

    @api.onchange('type', 'is_ssl')
    def onchange_server_type(self):
        super().onchange_server_type()
