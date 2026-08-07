# -*- coding: utf-8 -*-
"""ai.playground — send a test prompt to any configured provider and see output."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AiPlayground(models.TransientModel):
    _name = 'ai.playground'
    _description = 'AI Playground'

    provider_id = fields.Many2one(
        'ai.provider', string='Provider', required=True,
        domain=[('credential_ids.state', '=', 'connected')],
        help="Only providers with a connected credential are listed — "
             "add a credential and Test/Connect it to use it here.")
    provider_supports_vision = fields.Boolean(related='provider_id.supports_vision')
    mode = fields.Selection(
        [('chat', 'Chat'), ('image', 'Image'), ('video', 'Video')],
        string='Mode', default='chat', required=True,
        help="Chat = text completion. Image/Video = media generation via the "
             "provider's images/videos endpoint (e.g. xAI grok-imagine-image / "
             "grok-imagine-video).")
    credential_id = fields.Many2one('ai.credential', string='Credential')
    model_ref_id = fields.Many2one(
        'ai.model', string='Model (catalog)',
        domain="[('provider_id', '=', provider_id), ('is_image_model', '=', mode == 'image')]")
    model = fields.Char(string='Model', required=True,
                        help="Model id. Pick from the catalog or type one.")
    system_prompt = fields.Text(string='System Prompt')
    user_prompt = fields.Text(string='User Message', required=True, default='Say hello in one short sentence.')
    temperature = fields.Float(string='Temperature', default=0.7)
    max_tokens = fields.Integer(string='Max Tokens', default=512)
    stream = fields.Boolean(string='Stream')
    image = fields.Binary(string='Image (vision)')
    image_filename = fields.Char()

    response = fields.Text(string='Response', readonly=True)
    tool_calls_text = fields.Text(string='Tool Calls', readonly=True)
    usage_text = fields.Char(string='Usage', readonly=True)
    result_image = fields.Binary(string='Generated Image', readonly=True, attachment=False)
    result_image_filename = fields.Char()
    result_video_url = fields.Char(string='Generated Video URL', readonly=True)

    def _default_model_for_mode(self):
        """Sensible default model for the current (provider, mode).

        Image/Video use the provider's declared media model; Chat prefers the
        aux/fallback chat model over the catalog's alphabetical-first entry
        (which can be a specialised model like codex 'codex-auto-review')."""
        self.ensure_one()
        from ..tools import media_gen
        prov = self.provider_id
        if self.mode == 'image':
            return (prov.default_image_model if prov else False) or media_gen.DEFAULT_IMAGE_MODEL
        if self.mode == 'video':
            return (prov.default_video_model if prov else False) or media_gen.DEFAULT_VIDEO_MODEL
        if prov:
            return (prov.default_aux_model or (prov.get_fallback_models() or [''])[0]
                    or prov.model_ids[:1].model_id)
        return False

    @api.onchange('provider_id')
    def _onchange_provider(self):
        for wiz in self:
            if not wiz.provider_id:
                continue
            cred = wiz.provider_id.credential_ids.filtered('is_default')[:1] \
                or wiz.provider_id.credential_ids[:1]
            wiz.credential_id = cred
            wiz.model = wiz._default_model_for_mode()

    @api.onchange('model_ref_id')
    def _onchange_model_ref(self):
        for wiz in self:
            if wiz.model_ref_id:
                wiz.model = wiz.model_ref_id.model_id

    @api.onchange('mode')
    def _onchange_mode(self):
        for wiz in self:
            wiz.model = wiz._default_model_for_mode()

    def _build_messages(self):
        self.ensure_one()
        messages = []
        if self.system_prompt:
            messages.append({'role': 'system', 'content': self.system_prompt})
        if self.image:
            ext = (self.image_filename or 'png').rsplit('.', 1)[-1].lower()
            mime = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png',
                    'gif': 'gif', 'webp': 'webp'}.get(ext, 'png')
            b64 = self.image.decode() if isinstance(self.image, bytes) else self.image
            messages.append({'role': 'user', 'content': [
                {'type': 'text', 'text': self.user_prompt or ''},
                {'type': 'image_url',
                 'image_url': {'url': f'data:image/{mime};base64,{b64}'}},
            ]})
        else:
            messages.append({'role': 'user', 'content': self.user_prompt or ''})
        return messages

    def action_run(self):
        self.ensure_one()
        if not self.model:
            raise UserError(_("Pick or type a model first."))
        if self.mode in ('image', 'video'):
            return self._run_media()
        messages = self._build_messages()
        connector = self.env['ai.connector']
        if self.stream:
            parts, final = [], {}
            for chunk in connector.chat(
                    provider=self.provider_id, model=self.model, messages=messages,
                    credential=self.credential_id or None, temperature=self.temperature,
                    max_tokens=self.max_tokens or None, stream=True):
                if chunk.get('delta'):
                    parts.append(chunk['delta'])
                if chunk.get('done'):
                    final = chunk
            self.response = ''.join(parts)
            usage = final.get('usage') or {}
            self.tool_calls_text = self._format_tool_calls(final.get('tool_calls'))
        else:
            result = connector.chat(
                provider=self.provider_id, model=self.model, messages=messages,
                credential=self.credential_id or None, temperature=self.temperature,
                max_tokens=self.max_tokens or None)
            self.response = result.get('content') or ''
            usage = result.get('usage') or {}
            self.tool_calls_text = self._format_tool_calls(result.get('tool_calls'))
        if usage:
            self.usage_text = _(
                "prompt=%(p)s  completion=%(c)s  total=%(t)s",
                p=usage.get('prompt_tokens', 0), c=usage.get('completion_tokens', 0),
                t=usage.get('total_tokens', 0))
        return self._reopen_form()

    def _run_media(self):
        """Image/video generation branch of the Playground Run button."""
        connector = self.env['ai.connector']
        prov = self.provider_id
        if self.mode == 'image' and not prov.supports_image_gen:
            raise UserError(_(
                "Provider '%s' can't generate images. Use xAI (Grok) or OpenAI Codex.",
                prov.name))
        if self.mode == 'video' and not prov.supports_video_gen:
            raise UserError(_(
                "Provider '%s' can't generate videos. Use xAI (Grok).", prov.name))
        # Clear any prior result so the form doesn't show stale output.
        self.response = False
        self.result_image = False
        self.result_video_url = False
        self.tool_calls_text = False
        self.usage_text = False
        if not self.user_prompt:
            raise UserError(_("Enter a prompt describing the image/video."))
        if self.mode == 'image':
            res = connector.generate_image(
                provider=self.provider_id, model=self.model, prompt=self.user_prompt,
                credential=self.credential_id or None)
            images = res.get('images') or []
            if images:
                self.result_image = images[0].get('b64')
                ext = (images[0].get('mimetype') or 'image/png').split('/')[-1]
                self.result_image_filename = 'image.%s' % ext
                self.response = _("Generated %s image(s).", len(images))
        else:  # video
            res = connector.generate_video(
                provider=self.provider_id, model=self.model, prompt=self.user_prompt,
                credential=self.credential_id or None)
            self.result_video_url = res.get('video_url') or ''
            self.response = _("Video ready (status: %s).", res.get('status') or 'done')
        return self._reopen_form()

    def _reopen_form(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Playground'),
            'res_model': 'ai.playground',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @staticmethod
    def _format_tool_calls(tool_calls):
        if not tool_calls:
            return False
        lines = []
        for tc in tool_calls:
            fn = tc.get('function') or {}
            lines.append(f"{fn.get('name')}({fn.get('arguments')})")
        return '\n'.join(lines)
