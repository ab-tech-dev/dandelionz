"""
Flexible (running-balance) installment payments: pay any amount, from wallet or card, anytime,
with early payoff and a ship threshold - the CDcare model.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from transactions.models import (
    InstallmentCharge, InstallmentPayment, InstallmentPlan, LedgerEntry, Order, Wallet,
)
from users.models import Customer

User = get_user_model()


@patch('transactions.installment_payment.Paystack')
class FlexibleInstallmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email='ip@test.com', password='pass12345', role='CUSTOMER', full_name='IP',
        )
        Customer.objects.get_or_create(user=self.customer)
        self.wallet, _ = Wallet.objects.get_or_create(user=self.customer)
        self.client.force_authenticate(user=self.customer)

    def _make_plan(self, total=Decimal('6000.00'), n=3, first_due_in_days=30):
        order = Order.objects.create(
            customer=self.customer, total_price=total,
            status=Order.Status.PENDING, payment_status='UNPAID',
        )
        base = (total / n).quantize(Decimal('0.01'), rounding='ROUND_DOWN')
        remainder = total - base * n
        plan = InstallmentPlan.objects.create(
            order=order, duration='3_months', total_amount=total,
            installment_amount=base, number_of_installments=n, status='ACTIVE',
        )
        now = timezone.now()
        for i in range(1, n + 1):
            # First row at `first_due_in_days`, each subsequent row 30 days later. A negative
            # first offset puts only the first row(s) in the past.
            InstallmentPayment.objects.create(
                installment_plan=plan, payment_number=i,
                amount=(base + remainder if i == n else base),
                due_date=now + timedelta(days=first_due_in_days + 30 * (i - 1)),
                reference=f"{order.order_id}-inst-{i}",
            )
        return plan

    def _fund(self, amount):
        self.wallet.credit(amount, source='t', bucket=LedgerEntry.Bucket.SPENDABLE,
                           entry_type=LedgerEntry.EntryType.DEPOSIT)
        self.wallet.refresh_from_db()

    def _init(self, plan, **body):
        return self.client.post(reverse('init-installment-payment'),
                                {'plan_id': plan.id, **body}, format='json')

    def _mock_init(self, Paystack):
        Paystack.return_value.initialize_payment.return_value = {'data': {'authorization_url': 'https://p.test/x'}}

    def _mock_verify(self, Paystack, amount, txn_id=1):
        Paystack.return_value.verify_payment.return_value = {
            'data': {'status': 'success', 'currency': 'NGN',
                     'amount': int(Decimal(str(amount)) * 100), 'id': txn_id}
        }

    def test_pay_arbitrary_amount_by_card(self, Paystack):
        plan = self._make_plan()
        self._mock_init(Paystack)
        resp = self._init(plan, amount='1000')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['data']['requires_payment'])
        reference = resp.data['data']['reference']

        self._mock_verify(Paystack, Decimal('1000'))
        self.client.get(reverse('verify-installment-payment'), {'reference': reference})
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('1000.00'))
        self.assertEqual(plan.balance_remaining, Decimal('5000.00'))

    def test_pay_from_wallet_settles_immediately(self, Paystack):
        plan = self._make_plan()
        self._fund(Decimal('3000'))
        resp = self._init(plan, amount='2000', use_wallet=True)
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.data['data']['requires_payment'])
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('2000.00'))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1000.00'))

    def test_clear_balance_completes_the_plan(self, Paystack):
        plan = self._make_plan()
        self._mock_init(Paystack)
        resp = self._init(plan, clear_balance=True)
        self.assertEqual(resp.data['data']['amount'], 6000.0)
        self._mock_verify(Paystack, Decimal('6000'))
        self.client.get(reverse('verify-installment-payment'), {'reference': resp.data['data']['reference']})
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'COMPLETED')
        self.assertEqual(plan.balance_remaining, Decimal('0.00'))

    def test_overpay_is_rejected(self, Paystack):
        plan = self._make_plan()
        resp = self._init(plan, amount='7000')
        self.assertEqual(resp.status_code, 400)

    def test_minimum_enforced_once_a_due_date_has_passed(self, Paystack):
        # Only the first installment is due (5 days ago); minimum is that installment (2000).
        plan = self._make_plan(first_due_in_days=-5)
        self.assertEqual(plan.minimum_due_now(), Decimal('2000.00'))
        too_small = self._init(plan, amount='500')
        self.assertEqual(too_small.status_code, 400)
        self._mock_init(Paystack)
        ok = self._init(plan, amount='2000')
        self.assertEqual(ok.status_code, 201)

    def test_any_amount_allowed_before_a_due_date(self, Paystack):
        plan = self._make_plan(first_due_in_days=30)  # nothing due yet
        self.assertEqual(plan.minimum_due_now(), Decimal('0.00'))
        self._mock_init(Paystack)
        resp = self._init(plan, amount='300')
        self.assertEqual(resp.status_code, 201)

    def test_partial_payment_does_not_release_fulfillment(self, Paystack):
        """Ship threshold is 100% - a half-paid plan must not become fulfillment-eligible."""
        plan = self._make_plan()  # total 6000
        self._mock_init(Paystack)
        resp = self._init(plan, amount='3000')
        self._mock_verify(Paystack, Decimal('3000'))
        self.client.get(reverse('verify-installment-payment'), {'reference': resp.data['data']['reference']})
        plan.refresh_from_db()
        self.assertFalse(plan.fulfillment_released)
        plan.order.refresh_from_db()
        self.assertEqual(plan.order.status, Order.Status.PENDING)

    def test_ship_threshold_releases_fulfillment(self, Paystack):
        plan = self._make_plan()  # total 6000, threshold 1.0 -> full amount
        self._mock_init(Paystack)
        resp = self._init(plan, amount='6000')
        self._mock_verify(Paystack, Decimal('6000'))
        self.client.get(reverse('verify-installment-payment'), {'reference': resp.data['data']['reference']})
        plan.refresh_from_db()
        self.assertTrue(plan.fulfillment_released)
        plan.order.refresh_from_db()
        self.assertEqual(plan.order.status, Order.Status.PAID)

    def test_paying_a_fully_paid_plan_is_rejected(self, Paystack):
        plan = self._make_plan()
        self._fund(Decimal('6000'))
        self._init(plan, clear_balance=True, use_wallet=True)  # pays it all off from wallet
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'COMPLETED')
        # A further payment attempt must be refused (plan no longer ACTIVE / nothing owed).
        resp = self._init(plan, amount='1000')
        self.assertEqual(resp.status_code, 400)

    @patch('authentication.views_admin.send_order_notification', lambda *a, **k: True)
    @patch('transactions.delivery_payment.Paystack')
    def test_installment_order_enters_the_delivery_flow_at_full_payment(self, DeliveryPaystack, Paystack):
        """Once fully paid the order must satisfy the delivery flow's payment_status/status gates
        so the admin can schedule delivery and the customer can pay the fee."""
        plan = self._make_plan()  # total 6000, threshold 1.0 -> full amount
        self._mock_init(Paystack)
        r = self._init(plan, amount='6000')
        self._mock_verify(Paystack, Decimal('6000'))
        self.client.get(reverse('verify-installment-payment'), {'reference': r.data['data']['reference']})

        order = plan.order
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_status, 'PAID')

        # Admin can now schedule delivery on the fully-paid installment order.
        admin = User.objects.create_user(email='dadm@test.com', password='pass12345', role=User.Role.BUSINESS_ADMIN)
        self.client.force_authenticate(user=admin)
        dresp = self.client.patch(
            reverse('admin-orders-set-delivery', kwargs={'order_id': order.order_id}),
            {'use_default': True, 'delivery_fee': '1500.00'}, format='json',
        )
        self.assertEqual(dresp.status_code, 200)

        # And the customer can pay that delivery fee (the gate that worried us).
        self.client.force_authenticate(user=self.customer)
        DeliveryPaystack.return_value.initialize_payment.return_value = {'data': {'authorization_url': 'https://p.test/d'}}
        presp = self.client.post(
            reverse('init-delivery-payment', kwargs={'order_id': order.order_id}), {}, format='json',
        )
        self.assertEqual(presp.status_code, 200)
        self.assertTrue(presp.data['data']['requires_payment'])

    def test_wallet_insufficient_is_rejected(self, Paystack):
        plan = self._make_plan()
        self._fund(Decimal('1000'))
        resp = self._init(plan, amount='2000', use_wallet=True)
        self.assertEqual(resp.status_code, 400)
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('0.00'))

    def test_schedule_rows_reconcile_to_the_running_balance(self, Paystack):
        plan = self._make_plan()  # 3 x 2000
        self._mock_init(Paystack)
        r1 = self._init(plan, amount='2000')
        self._mock_verify(Paystack, Decimal('2000'))
        self.client.get(reverse('verify-installment-payment'), {'reference': r1.data['data']['reference']})
        # After 2000: row 1 covered.
        statuses = list(plan.installments.order_by('payment_number').values_list('status', flat=True))
        self.assertEqual(statuses, ['PAID', 'PENDING', 'PENDING'])

        r2 = self._init(plan, amount='3000')
        self._mock_verify(Paystack, Decimal('3000'), txn_id=2)
        self.client.get(reverse('verify-installment-payment'), {'reference': r2.data['data']['reference']})
        # After 5000: rows 1 and 2 covered (cumulative 4000 <= 5000), row 3 not (6000 > 5000).
        statuses = list(plan.installments.order_by('payment_number').values_list('status', flat=True))
        self.assertEqual(statuses, ['PAID', 'PAID', 'PENDING'])

    def test_restarting_cancels_the_prior_pending_charge(self, Paystack):
        plan = self._make_plan()
        self._mock_init(Paystack)
        first = self._init(plan, amount='1000')
        old_ref = first.data['data']['reference']
        self._init(plan, amount='1500')
        old = InstallmentCharge.objects.get(reference=old_ref)
        self.assertEqual(old.status, InstallmentCharge.Status.CANCELLED)
        self.assertEqual(
            plan.charges.filter(status=InstallmentCharge.Status.PENDING).count(), 1
        )

    def test_plan_serializer_exposes_running_balance(self, Paystack):
        plan = self._make_plan()
        self._fund(Decimal('2000'))
        self._init(plan, amount='2000', use_wallet=True)  # settles now
        resp = self.client.get(reverse('installment-plan-detail', kwargs={'id': plan.id}))
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data'] if 'data' in resp.data else resp.data
        self.assertEqual(float(data['amount_paid']), 2000.0)
        self.assertEqual(data['balance_remaining'], 4000.0)
        self.assertAlmostEqual(data['paid_fraction'], 0.3333, places=3)
        self.assertIsNotNone(data['next_due_date'])

    def test_admin_can_list_all_plans(self, Paystack):
        plan = self._make_plan()
        admin = User.objects.create_user(email='ipadmin@test.com', password='pass12345', role=User.Role.BUSINESS_ADMIN)
        self.client.force_authenticate(user=admin)
        resp = self.client.get(reverse('installment-plan-list'))
        self.assertEqual(resp.status_code, 200)
        rows = resp.data['data'] if 'data' in resp.data else resp.data
        rows = rows.get('results', rows) if isinstance(rows, dict) else rows
        self.assertTrue(any(r['id'] == plan.id for r in rows))

    def test_paying_a_replaced_link_refunds_to_source(self, Paystack):
        plan = self._make_plan()
        self._mock_init(Paystack)
        first = self._init(plan, amount='1000')
        old_ref = first.data['data']['reference']
        self._init(plan, amount='1500')  # cancels the first

        self._mock_verify(Paystack, Decimal('1000'), txn_id=99)
        Paystack.return_value.refund.return_value = {'data': {'id': 555}}
        resp = self.client.get(reverse('verify-installment-payment'), {'reference': old_ref})
        self.assertEqual(resp.status_code, 400)
        Paystack.return_value.refund.assert_called_once()
        old = InstallmentCharge.objects.get(reference=old_ref)
        self.assertEqual(old.status, InstallmentCharge.Status.REFUNDED)
        plan.refresh_from_db()
        self.assertEqual(plan.amount_paid, Decimal('0.00'))
