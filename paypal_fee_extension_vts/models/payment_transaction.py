# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.addons.payment import utils as payment_utils


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _paypal_prepare_order_payload(self):
        payload = super(PaymentTransaction, self)._paypal_prepare_order_payload()
        # Ensure structure exists
        purchase_units = payload.get("purchase_units") or []
        if not purchase_units:
            return payload
        amount = purchase_units[0].get("amount") or {}
        #total_amount = payment_utils.to_minor_currency_units(self.amount + self.fees, self.currency_id)
        total_amount = self.amount + self.fees
        breakdown = {
            "item_total": {
                "currency_code": self.currency_id.name,
                "value": total_amount - self.fees,
            },
            "handling": {
                "currency_code": self.currency_id.name,
                "value": self.fees,
            },
        }
        amount['value'] = total_amount
        amount['breakdown'] = breakdown
        purchase_units[0]["amount"] = amount
        return payload

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != 'paypal' or not self.fees:
            return super()._extract_amount_data(payment_data)

        amount_data = payment_data.get('amount', {})
        amount = float(amount_data.get("value", 0.0))
        currency_code = amount_data.get('currency_code')

        return {
            "amount": amount - self.fees,
            'currency_code': currency_code,
        }