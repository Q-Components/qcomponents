# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.addons.payment import utils as payment_utils


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _stripe_prepare_payment_intent_payload(self):
        """Prepare the payload for the creation of a payment intent in Stripe format.

        Note: This method serves as a hook for modules that would fully implement Stripe Connect.
        Note: self.ensure_one()

        :return: The Stripe-formatted payload for the payment intent request
        :rtype: dict
        """

        res = super(PaymentTransaction, self)._stripe_prepare_payment_intent_payload()
        res.update(
            {
                "amount": payment_utils.to_minor_currency_units(
                    self.amount + self.fees, self.currency_id
                ),
            }
        )
        return res

    def _extract_amount_data(self, payment_data):
        """Override of payment to extract the amount and currency from the payment data."""
        if self.provider_code != "stripe" or not self.fees:
            return super()._extract_amount_data(payment_data)

        if self.operation == "refund":
            payment_data = payment_data["refund"]
        else:  # 'online_direct', 'online_token', 'offline'
            payment_data = payment_data["payment_intent"]
        amount = payment_utils.to_major_currency_units(
            payment_data.get("amount", 0), self.currency_id
        )
        currency_code = payment_data.get("currency", "").upper()
        return {
            "amount": amount - self.fees,
            "currency_code": currency_code,
        }
