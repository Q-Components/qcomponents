from markupsafe import Markup

from odoo import Command, fields, models, _


def _fmt_address(street, street2, city, state, zip_code, country):
    parts = [
        ", ".join(filter(None, [street, street2])),
        city,
        " ".join(filter(None, [state, zip_code])),
        country,
    ]
    return ", ".join(p for p in parts if p)


def _norm(value):
    return " ".join((value or "").upper().split())


def _build_comparison_html(partner, candidates):
    """Table: current address next to every FedEx suggestion.
    Values FedEx changed are highlighted. All values are escaped by Markup."""
    current = {
        'street': partner.street or '',
        'street2': partner.street2 or '',
        'city': partner.city or '',
        'state_code': partner.state_id.code or '',
        'zip': partner.zip or '',
        'country_code': partner.country_id.code or '',
    }
    suggestions = [{k: (c.get(k) or '') for k in current} for c in candidates]
    rows = [
        ('street', _("Street")),
        ('street2', _("Apt / Suite")),
        ('city', _("City")),
        ('state_code', _("State")),
        ('zip', _("ZIP")),
        ('country_code', _("Country")),
    ]

    head = [Markup('<th style="width:18%"></th>'),
            Markup('<th>%s</th>') % _("Current address")]
    for idx in range(len(suggestions)):
        title = _("FedEx suggested address") if len(suggestions) == 1 \
            else _("FedEx suggestion %s", idx + 1)
        head.append(Markup('<th class="text-success">%s</th>') % title)

    body = []
    for key, title in rows:
        if not current[key] and not any(s[key] for s in suggestions):
            continue   # e.g. no second street line anywhere: skip the row
        cells = [Markup('<th class="text-muted fw-normal">%s</th>') % title,
                 Markup('<td>%s</td>') % (current[key] or '—')]
        for s in suggestions:
            if _norm(s[key]) != _norm(current[key]):
                cells.append(Markup('<td class="table-warning fw-bold">%s</td>')
                             % (s[key] or '—'))
            else:
                cells.append(Markup('<td>%s</td>') % (s[key] or '—'))
        body.append(Markup('<tr>%s</tr>') % Markup('').join(cells))

    html = Markup(
        '<table class="table table-sm table-bordered align-middle mb-2">'
        '<thead class="table-light"><tr>%s</tr></thead><tbody>%s</tbody></table>'
    ) % (Markup('').join(head), Markup('').join(body))
    if suggestions:
        html += Markup('<div class="text-muted small">%s</div>') % _(
            "Highlighted values are what FedEx changed.")
    return html


class FedexAddressWizard(models.TransientModel):
    _name = 'fedex.address.wizard'
    _description = 'FedEx Address Validation'

    picking_id = fields.Many2one('stock.picking', string="Delivery Order",
                                 required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string="Customer",
                                 required=True, ondelete='cascade')
    status = fields.Char(readonly=True)
    messages = fields.Text(readonly=True)
    has_suggestion = fields.Boolean(readonly=True)
    comparison_html = fields.Html(readonly=True, sanitize=False)
    line_ids = fields.One2many('fedex.address.wizard.line', 'wizard_id')
    selected_line_id = fields.Many2one(
        'fedex.address.wizard.line', string="Address to use",
        domain="[('wizard_id', '=', id)]")

    def open_from_result(self, picking, res):
        partner = picking.partner_id
        candidates = res.get('candidates') or []

        line_cmds = [Command.create({
            'is_current': True,
            'label': _("Keep current address"),
            'full_address': _fmt_address(
                partner.street, partner.street2, partner.city,
                partner.state_id.code, partner.zip, partner.country_id.code),
        })]
        for idx, c in enumerate(candidates, start=1):
            line_cmds.append(Command.create({
                'street': c.get('street'), 'street2': c.get('street2'),
                'city': c.get('city'), 'state_code': c.get('state_code'),
                'zip': c.get('zip'), 'country_code': c.get('country_code'),
                'label': _("Use FedEx suggested address") if len(candidates) == 1
                         else _("Use FedEx suggestion %s", idx),
                'full_address': _fmt_address(
                    c.get('street'), c.get('street2'), c.get('city'),
                    c.get('state_code'), c.get('zip'), c.get('country_code')),
            }))

        wiz = self.create({
            'picking_id': picking.id,
            'partner_id': partner.id,
            'status': _("FedEx suggests a corrected address.") if candidates
                      else _("FedEx could not verify this address."),
            'messages': "\n".join(m for m in res['messages'] if m),
            'has_suggestion': bool(candidates),
            'comparison_html': _build_comparison_html(partner, candidates),
            'line_ids': line_cmds,
        })
        # Safe default: keep the current address unless the user picks another
        wiz.selected_line_id = wiz.line_ids.filtered('is_current')[:1]
        return {
            'type': 'ir.actions.act_window',
            'name': _("Check Delivery Address"),
            'res_model': self._name,
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'dialog_size': 'large'},
        }

    def action_confirm(self):
        """Apply the chosen address (if it is a FedEx one), then continue the
        delivery validation, which creates the FedEx shipment in the same click."""
        self.ensure_one()
        picking = self.picking_id
        line = self.selected_line_id
        if line and not line.is_current:
            picking.carrier_id._fedex_apply_suggested_address(self.partner_id, {
                'street': line.street, 'street2': line.street2, 'city': line.city,
                'state_code': line.state_code, 'zip': line.zip,
                'country_code': line.country_code,
            })
            picking.message_post(body=_(
                "FedEx address validation: customer address updated to %s",
                line.full_address))
        else:
            picking.message_post(body=_(
                "FedEx address validation: user continued with the current address."))

        picking.fedex_av_checked = True
        res = picking.with_context(fedex_av_skip=True).button_validate()
        return res if isinstance(res, dict) else {'type': 'ir.actions.act_window_close'}


class FedexAddressWizardLine(models.TransientModel):
    _name = 'fedex.address.wizard.line'
    _description = 'FedEx Address Option'
    _rec_name = 'label'

    wizard_id = fields.Many2one('fedex.address.wizard', ondelete='cascade')
    label = fields.Char(readonly=True)
    full_address = fields.Char(readonly=True)
    is_current = fields.Boolean(readonly=True)
    street = fields.Char(readonly=True)
    street2 = fields.Char(readonly=True)
    city = fields.Char(readonly=True)
    state_code = fields.Char(readonly=True)
    zip = fields.Char(readonly=True)
    country_code = fields.Char(readonly=True)
