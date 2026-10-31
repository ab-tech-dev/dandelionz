"""
Installment card payments arrive on the main Paystack webhook.

Paystack allows one webhook URL per mode, and it points at /transactions/webhook/. An `INS-`
charge.success therefore has to be settled there; it used to be dropped as "installment
handled elsewhere", which left a customer who closed the page before the verify call charged
but not credited.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from transactions.models import (
    InstallmentCharge, InstallmentPayment, InstallmentPlan, Order, PaystackEvent, Wallet,
)

User = get_user_model()
SECRET = 'sk_test_dummy_secret'


def sign(body):
    return hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()


@override_settings(PAYSTACK_SECRET_KEY=SECRET)
class InstallmentWebhookTests(TestCase):
    url = '/transactions/webhook/'

    def setUp(self):
        self.user = User.objects.create_user(
            email='inst@test.com', password='pass12345', role='CUSTOMER', full_name='Inst',
        )
        Wallet.objects.get_or_create(user=self.user)
        self.order = Order.objects.create(
            customer=self.user, total_price=Decimal('6000.00'), payment_status='UNPAID',
        )
        self.plan = InstallmentPlan.objects.create(
            order=self.order, duration='3_months', total_amount=Decimal('6000.00'),
            installment_amount=Decimal('2000.00'), number_of_installments=3, status='ACTIVE',
        )
        for i in range(1, 4):
            InstallmentPayment.objects.create(
                installment_plan=self.plan, payment_number=i, amount=Decimal('2000.00'),
                due_date=timezone.now() + timedelta(days=30 * i),
                reference=f"{self.order.order_id}-installment-{i}",
            )
        self.charge = InstallmentCharge.objects.create(
            plan=self.plan, reference='INS-1-webhooktest', amount=Decimal('2000.00'),
            method=InstallmentCharge.Method.CARD,
        )

    def _post(self, event_id=1, reference='INS-1-webhooktest'):
        body = json.dumps({
            'id': event_id, 'event': 'charge.success', 'data': {'reference': reference},
        }).encode()
        return self.client.post(
            self.url, data=body, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=sign(body),
        )

    def _verify(self, status='success', amount=200000, currency='NGN', reference='INS-1-webhooktest'):
        return {'data': {
            'status': status, 'amount': amount, 'currency': currency,
            'reference': reference, 'id': 424242,
        }}

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_paid_installment_is_settled_by_the_webhook_alone(self, verify):
        verify.return_value = self._verify()
        response = self._post()

        self.assertEqual(response.status_code, 200)
        self.charge.refresh_from_db()
        self.plan.refresh_from_db()
        self.assertEqual(self.charge.status, InstallmentCharge.Status.PAID)
        self.assertEqual(self.plan.amount_paid, Decimal('2000.00'))
        event = PaystackEvent.objects.get(event_id='charge.success:1')
        self.assertEqual(event.status, PaystackEvent.Status.PROCESSED)

    @patch('transactions.views.Paystack.verify_payment')
    def test_redelivery_and_the_verify_endpoint_never_double_credit(self, verify):
        verify.return_value = self._verify()
        self._post(event_id=1)
        self._post(event_id=1)   # Paystack retry of the same event
        self._post(event_id=2)   # a different event for the same payment
        # The app's own verify call settling it as well.
        from transactions import installment_payment as inst
        inst.settle_installment_charge(self.charge)

        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('2000.00'))
        self.assertEqual(InstallmentCharge.objects.filter(status='PAID').count(), 1)

    @patch('transactions.views.Paystack.verify_payment')
    def test_an_unsuccessful_payment_is_not_credited(self, verify):
        verify.return_value = self._verify(status='failed')
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('0.00'))
        self.charge.refresh_from_db()
        self.assertNotEqual(self.charge.status, InstallmentCharge.Status.PAID)

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_wrong_currency_is_not_credited(self, verify):
        verify.return_value = self._verify(currency='USD')
        self._post()
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_wrong_amount_is_not_credited(self, verify):
        verify.return_value = self._verify(amount=100)  # N1.00, not N2000
        self._post()
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment', side_effect=RuntimeError('paystack down'))
    def test_a_paystack_outage_returns_200_and_credits_nothing(self, verify):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_an_unknown_installment_reference_is_ignored_safely(self, verify):
        verify.return_value = self._verify(reference='INS-9-nosuchcharge')
        response = self._post(reference='INS-9-nosuchcharge')
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('0.00'))

    def test_a_forged_event_is_rejected(self):
        body = json.dumps({
            'id': 5, 'event': 'charge.success', 'data': {'reference': 'INS-1-webhooktest'},
        }).encode()
        response = self.client.post(
            self.url, data=body, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='forged',
        )
        self.assertEqual(response.status_code, 403)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.amount_paid, Decimal('0.00'))
