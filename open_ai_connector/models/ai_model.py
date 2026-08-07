# -*- coding: utf-8 -*-
"""ai.model — per-provider model catalog.

Populated either from a provider's curated ``fallback_models`` (seed) or from a
live ``/models`` fetch. Used by the picker and the gateway's model routing.
"""
from odoo import api, fields, models


class AiModel(models.Model):
    _name = 'ai.model'
    _description = 'AI Model'
    _order = 'provider_id, model_id'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    provider_id = fields.Many2one(
        'ai.provider', string='Provider', required=True, ondelete='cascade', index=True)
    provider_code = fields.Char(related='provider_id.code', store=True, index=True)
    model_id = fields.Char(string='Model ID', required=True, index=True)
    context_window = fields.Integer(string='Context Window')
    supports_tools = fields.Boolean(string='Supports Tools', default=True)
    supports_vision = fields.Boolean(string='Supports Vision')
    is_image_model = fields.Boolean(
        string='Image Model', index=True,
        help="This is an image-generation model (e.g. gpt-image-2, grok-imagine-image), "
             "not a chat/completion model. Used by AI Image Studio's model picker.")
    active = fields.Boolean(default=True)

    # v19: _sql_constraints is no longer honoured — use model.Constraint.
    _provider_model_uniq = models.Constraint(
        'unique(provider_id, model_id)',
        'A model ID must be unique per provider.')

    @api.depends('provider_id.code', 'model_id')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.provider_id.code or '?'} / {rec.model_id or ''}"

    @api.model
    def _upsert(self, provider, model_ids):
        """Insert any model_ids not already present for *provider*.

        Returns ``(added, total)``: how many were newly created and the total
        number of distinct models synced (so callers can say "N available,
        X new" instead of an alarming "0 added" on a repeat fetch).
        """
        ids = [m for m in dict.fromkeys(model_ids or []) if m]
        if not ids:
            return (0, 0)
        existing = set(self.search([
            ('provider_id', '=', provider.id),
            ('model_id', 'in', ids),
        ]).mapped('model_id'))
        to_add = [m for m in ids if m not in existing]
        if to_add:
            self.create([
                {'provider_id': provider.id, 'model_id': m} for m in to_add
            ])
        return (len(to_add), len(ids))
