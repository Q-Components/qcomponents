# -*- coding: utf-8 -*-

from werkzeug import urls

from odoo import models, fields, api, _


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    fees = fields.Monetary(
        string="Fees",
        currency_field="currency_id",
        help="The fees amount; set by the system as it depends on the provider",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            provider = self.env["payment.provider"].browse(values["provider_id"])
            partner = self.env["res.partner"].browse(values["partner_id"])
            if values.get("operation") == "validation":
                values["fees"] = 0
            else:
                currency = (
                    self.env["res.currency"].browse(values.get("currency_id")).exists()
                )
                values["fees"] = provider._compute_fees(
                    values.get("amount", 0),
                    partner.country_id,
                )
        txs = super().create(values_list)
        txs.invalidate_recordset(["amount", "fees"])
        return txs
