from odoo import models, fields


class ProcessedEmails(models.Model):
    _name = 'processed.emails'
    _description = 'Processed Email List'

    server_id = fields.Many2one(
        comodel_name='fetchmail.server',
        string='Mail Server'
    )
    processed_email_id = fields.Char(
        string='Email ID'
    )