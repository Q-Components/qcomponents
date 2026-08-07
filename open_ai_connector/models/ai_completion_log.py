# -*- coding: utf-8 -*-
"""ai.completion.log — request/response + token-usage audit trail."""
from odoo import fields, models


class AiCompletionLog(models.Model):
    _name = 'ai.completion.log'
    _description = 'AI Completion Log'
    _order = 'create_date desc'
    _rec_name = 'model'

    provider_id = fields.Many2one('ai.provider', string='Provider', ondelete='set null', index=True)
    credential_id = fields.Many2one('ai.credential', string='Credential', ondelete='set null')
    model = fields.Char(string='Model', index=True)
    request_json = fields.Text(string='Request')
    response_text = fields.Text(string='Response')
    finish_reason = fields.Char(string='Finish Reason')
    prompt_tokens = fields.Integer(string='Prompt Tokens', aggregator='sum')
    completion_tokens = fields.Integer(string='Completion Tokens', aggregator='sum')
    total_tokens = fields.Integer(string='Total Tokens', aggregator='sum')
    duration_ms = fields.Integer(string='Duration (ms)')
    status = fields.Selection([('ok', 'OK'), ('error', 'Error')], string='Status', index=True)
    error = fields.Text(string='Error')
    user_id = fields.Many2one('res.users', string='User', index=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company, index=True)
