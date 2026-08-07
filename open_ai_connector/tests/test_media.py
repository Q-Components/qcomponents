# -*- coding: utf-8 -*-
import base64
import io
from unittest.mock import patch

from PIL import Image

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


def _png_bytes():
    """Raw PNG bytes (begins with the \\x89PNG signature)."""
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (10, 20, 30)).save(buf, format='PNG')
    return buf.getvalue()


@tagged('post_install', '-at_install', 'oconn_media')
class TestImageEdit(TransactionCase):
    """Image-to-image (remix) routing + capability gating on ai.connector.generate_image."""

    def _codex(self):
        return self.env.ref('open_ai_connector.provider_openai_codex')

    def test_codex_provider_has_edit_capability(self):
        self.assertTrue(self._codex().supports_image_edit)

    def test_image_models_flagged_and_excluded_from_chat_pickers(self):
        """Seeded image models must carry is_image_model and be excluded from the
        chat-model domain the bridge/gateway pickers use."""
        Model = self.env['ai.model']
        codex = self._codex()
        img = self.env.ref('open_ai_connector.imgmodel_codex_gpt_image_2_medium')
        self.assertTrue(img.is_image_model)
        # chat picker domain (is_image_model=False) must NOT list the image model
        chat = Model.search([('provider_id', '=', codex.id), ('is_image_model', '=', False)])
        self.assertNotIn(img, chat)
        # image picker domain (is_image_model=True) must list it
        imgs = Model.search([('provider_id', '=', codex.id), ('is_image_model', '=', True)])
        self.assertIn(img, imgs)

    def test_xai_provider_has_no_edit_capability(self):
        self.assertFalse(self.env.ref('open_ai_connector.provider_xai').supports_image_edit)

    def test_generate_image_edit_routes_to_codex_source_image(self):
        prov = self._codex()
        cred = self.env['ai.credential'].create({'name': 'c', 'provider_id': prov.id})
        captured = {}

        def fake_codex(base_url, headers, model, prompt, *, source_image=None, **kw):
            captured['source_image'] = source_image
            return {'images': [{'b64_json': 'QUJD', 'url': None, 'mime_type': 'image/png'}]}

        # Bypass real auth/HTTP: stub _media_proxy (auth.resolve) + _media_request.
        with patch.object(type(self.env['ai.connector']), '_media_proxy',
                          lambda self, p, c: None), \
             patch.object(type(self.env['ai.connector']), '_media_request',
                          lambda self, p, c, do: do({'Authorization': 'Bearer x'},
                                                    'https://example/v1')), \
             patch('odoo.addons.open_ai_connector.tools.codex_responses.generate_image_codex',
                   fake_codex):
            res = self.env['ai.connector'].generate_image(
                prov.code, 'gpt-image-2-medium', 'a cat', credential=cred.id,
                image='QUJD', mode='remix', log=False)
        self.assertEqual(captured['source_image'], 'QUJD')
        self.assertTrue(res['images'])

    def test_generate_image_no_image_does_not_remix(self):
        """mode='remix' but no source image -> treated as a normal generate (no gate)."""
        prov = self._codex()
        cred = self.env['ai.credential'].create({'name': 'c2', 'provider_id': prov.id})
        captured = {}

        def fake_codex(base_url, headers, model, prompt, *, source_image=None, **kw):
            captured['source_image'] = source_image
            return {'images': [{'b64_json': 'QUJD', 'url': None, 'mime_type': 'image/png'}]}

        with patch.object(type(self.env['ai.connector']), '_media_proxy',
                          lambda self, p, c: None), \
             patch.object(type(self.env['ai.connector']), '_media_request',
                          lambda self, p, c, do: do({'Authorization': 'Bearer x'},
                                                    'https://example/v1')), \
             patch('odoo.addons.open_ai_connector.tools.codex_responses.generate_image_codex',
                   fake_codex):
            self.env['ai.connector'].generate_image(
                prov.code, 'gpt-image-2-medium', 'a cat', credential=cred.id,
                mode='remix', log=False)
        self.assertIsNone(captured['source_image'])

    def test_generate_image_edit_rejected_when_unsupported(self):
        prov = self.env.ref('open_ai_connector.provider_xai')
        cred = self.env['ai.credential'].create({
            'name': 'x', 'provider_id': prov.id, 'api_key': 'sk-x'})
        with self.assertRaises(UserError):
            self.env['ai.connector'].generate_image(
                prov.code, 'grok-imagine-image', 'a cat', credential=cred.id,
                image='QUJD', mode='remix', log=False)

    def test_as_image_data_url_handles_bytes_from_image_field(self):
        """Odoo fields.Image reads back as base64-ASCII bytes — must not crash."""
        from odoo.addons.open_ai_connector.tools.codex_responses import _as_image_data_url
        b64_bytes = base64.b64encode(_png_bytes())          # bytes, like Image field
        out = _as_image_data_url(b64_bytes)
        self.assertIsInstance(out, str)
        self.assertTrue(out.startswith('data:image/png;base64,'))
        self.assertNotIn("b'", out)                         # no bytes-repr corruption

    def test_media_edit_decodes_base64_bytes_to_raw_png(self):
        """media_edit must upload decoded PNG bytes, not the base64 text."""
        from odoo.addons.open_ai_connector.tools import media_edit
        raw = _png_bytes()
        b64_bytes = base64.b64encode(raw)                   # bytes, like Image field
        captured = {}

        def fake_mp(url, *, headers=None, data=None, files=None, timeout=None, proxy_url=None):
            captured['content'] = files['image'][1]
            return {'data': [{'b64_json': 'QUJD', 'mime_type': 'image/png'}]}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_multipart',
                   side_effect=fake_mp):
            media_edit.edit_image('https://api.example/v1', {'Authorization': 'Bearer x'},
                                  'gpt-image-2', 'edit', b64_bytes)
        self.assertEqual(captured['content'], raw)          # decoded, not base64 text
        self.assertTrue(captured['content'].startswith(b'\x89PNG'))

    def test_media_edit_builds_images_edits_request(self):
        """media_edit.edit_image posts multipart to /images/edits and parses data[]."""
        from odoo.addons.open_ai_connector.tools import media_edit
        captured = {}

        def fake_mp(url, *, headers=None, data=None, files=None, timeout=None, proxy_url=None):
            captured['url'] = url
            captured['data'] = data
            captured['files'] = files
            return {'data': [{'b64_json': 'QUJD', 'mime_type': 'image/png'}]}

        with patch('odoo.addons.open_ai_connector.tools.http_client.post_multipart',
                   side_effect=fake_mp):
            out = media_edit.edit_image('https://api.example/v1', {'Authorization': 'Bearer x'},
                                        'gpt-image-2', 'make it blue', 'QUJD', size='1024x1024')
        self.assertTrue(captured['url'].endswith('/images/edits'))
        self.assertEqual(captured['data']['prompt'], 'make it blue')
        self.assertIn('image', captured['files'])
        self.assertEqual(out['images'][0]['b64_json'], 'QUJD')
