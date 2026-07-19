"""
Tests for customer payout settings and the withdrawal path they unblock.

Two live bugs are pinned here:

1. bank_code was never persisted for any role, so
   PayoutService.get_or_create_paystack_recipient always bailed at its blank-bank_code
   guard and no withdrawal could ever produce a transfer recipient.
2. process_external_transfer had no customer_profile branch, so even with bank details a
   customer payout had no recipient code and was always rejected.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from transactions.models import LedgerEntry, Wallet
from users.models import Customer, PaymentPIN, PayoutRequest, Vendor
from users.services.payment_settings import apply_payment_settings
from users.services.payout_service import PayoutService

User = get_user_model()


class CustomerPaymentSettingsEndpointTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='cust@test.com', password='test123', full_name='Cust User',
        )
        self.customer, _ = Customer.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_returns_empty_settings_before_any_are_saved(self):
        response = self.client.get('/user/customer/payment-settings/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['bank_name'], '')

    def test_put_persists_bank_details_including_bank_code(self):
        """bank_code is the field that was being silently dropped."""
        response = self.client.put('/user/customer/payment-settings/', {
            'bank_name': 'GTBank',
            'bank_code': '058',
            'account_number': '0123456789',
            'account_name': 'Cust User',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.bank_name, 'GTBank')
        self.assertEqual(self.customer.bank_code, '058')
        self.assertEqual(self.customer.account_number, '0123456789')

    def test_saved_settings_are_returned_on_a_subsequent_get(self):
        self.client.put('/user/customer/payment-settings/', {
            'bank_name': 'GTBank',
            'bank_code': '058',
            'account_number': '0123456789',
            'account_name': 'Cust User',
        }, format='json')

        response = self.client.get('/user/customer/payment-settings/')

        self.assertEqual(response.data['data']['bank_code'], '058')
        self.assertEqual(response.data['data']['account_number'], '0123456789')

    def test_non_customer_is_refused(self):
        """
        A vendor, not merely a user without a Customer row: ProfileResolver deliberately
        creates a missing profile for anyone whose role is CUSTOMER, so deleting the row
        is not enough to make someone a non-customer.
        """
        other = User.objects.create_user(
            email='nope@test.com', password='test123', full_name='Not Customer',
        )
        other.role = User.Role.VENDOR
        other.save(update_fields=['role'])
        Customer.objects.filter(user=other).delete()
        other = User.objects.get(pk=other.pk)

        client = APIClient()
        client.force_authenticate(user=other)

        response = client.get('/user/customer/payment-settings/')

        self.assertEqual(response.status_code, 403)


class PaymentSettingsHelperTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='helper@test.com', password='test123', full_name='Helper User',
        )
        self.customer, _ = Customer.objects.get_or_create(user=self.user)
        self.customer.bank_name = 'GTBank'
        self.customer.bank_code = '058'
        self.customer.account_number = '0123456789'
        self.customer.account_name = 'Helper User'
        self.customer.recipient_code = 'RCP_oldaccount'
        self.customer.save()

    def test_changing_the_account_number_clears_the_cached_recipient(self):
        """
        recipient_code points at one specific account at Paystack. Keeping it after the
        user switches accounts would send their next payout to the old one.
        """
        apply_payment_settings(self.customer, {'account_number': '9876543210'})

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.recipient_code, '')

    def test_changing_the_bank_clears_the_cached_recipient(self):
        apply_payment_settings(self.customer, {'bank_code': '044'})

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.recipient_code, '')

    def test_changing_only_the_account_name_keeps_the_recipient(self):
        """A display-name correction does not change where the money lands."""
        apply_payment_settings(self.customer, {'account_name': 'Helper U.'})

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.recipient_code, 'RCP_oldaccount')

    def test_resubmitting_identical_details_keeps_the_recipient(self):
        apply_payment_settings(self.customer, {
            'bank_code': '058',
            'account_number': '0123456789',
        })

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.recipient_code, 'RCP_oldaccount')


class CustomerWithdrawalCompletionTests(TestCase):
    """The end-to-end path that could not complete before."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='withdraw@test.com', password='test123', full_name='Withdraw User',
        )
        self.customer, _ = Customer.objects.get_or_create(user=self.user)
        self.customer.bank_name = 'GTBank'
        self.customer.bank_code = '058'
        self.customer.account_number = '0123456789'
        self.customer.account_name = 'Withdraw User'
        self.customer.save()

        # Re-fetch the user. The profile-creating signal caches a Customer instance on the
        # user's reverse-OneToOne, and ProfileResolver reads that cache - so without this
        # the view would see the pre-update instance with blank bank details.
        self.user = User.objects.get(pk=self.user.pk)

        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('5000.00'), source='Refund')

        pin = PaymentPIN.objects.create(user=self.user)
        pin.set_pin('1234')
        pin.save()

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_withdrawal_succeeds_with_only_amount_and_pin(self):
        """Matches the vendor contract - bank details come from saved settings."""
        response = self.client.post('/user/customer/wallet/withdraw/', {
            'amount': '1000.00',
            'pin': '1234',
        }, format='json')

        self.assertEqual(response.status_code, 200, msg=f"body: {response.data}")
        payout = PayoutRequest.objects.get(user=self.user)
        self.assertEqual(payout.amount, Decimal('1000.00'))

    def test_the_payout_snapshots_the_bank_code(self):
        """Without bank_code on the request, no Paystack recipient can be created."""
        self.client.post('/user/customer/wallet/withdraw/', {
            'amount': '1000.00',
            'pin': '1234',
        }, format='json')

        payout = PayoutRequest.objects.get(user=self.user)
        self.assertEqual(payout.bank_code, '058')

    def test_withdrawal_is_refused_when_no_payout_details_are_saved(self):
        self.customer.bank_name = ''
        self.customer.bank_code = ''
        self.customer.account_number = ''
        self.customer.account_name = ''
        self.customer.save()

        response = self.client.post('/user/customer/wallet/withdraw/', {
            'amount': '1000.00',
            'pin': '1234',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['reason'], 'payout_details_missing')

    @patch('users.services.payout_service.Paystack')
    def test_transfer_resolves_a_recipient_from_the_customer_profile(self, mock_paystack):
        """
        The core fix: process_external_transfer had no customer_profile branch, so this
        always returned "No transfer recipient code available".
        """
        mock_paystack.return_value.create_transfer_recipient.return_value = {
            'status': True,
            'data': {'recipient_code': 'RCP_newcustomer'},
        }
        mock_paystack.return_value.initiate_transfer.return_value = {
            'status': True,
            'data': {'status': 'success', 'reference': 'WTH-X'},
        }

        payout = PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            bank_code='058',
            account_number='0123456789',
            account_name='Withdraw User',
            reference='WTH-CUSTOMER1',
            status='processing',
        )

        success, result = PayoutService.process_external_transfer(payout)

        self.assertTrue(success, msg=f"transfer failed: {result}")

    def test_wallet_balance_endpoint_returns_buckets_and_the_minimum(self):
        """
        Also guards the endpoint actually executing - a missing `settings` import here
        would be a NameError that `manage.py check` cannot catch.
        """
        response = self.client.get('/user/customer/wallet/')

        self.assertEqual(response.status_code, 200)
        data = response.data['data']
        self.assertEqual(data['withdrawable_balance'], 5000.0)
        self.assertEqual(data['spendable_balance'], 0.0)
        self.assertEqual(data['min_withdrawal'], 500.0)

    def test_withdrawal_below_the_minimum_is_refused(self):
        """
        Enforced server-side because the clients disagreed (mobile 500, web 100) and the
        server previously accepted anything above zero, so a direct API call bypassed both.
        """
        response = self.client.post('/user/customer/wallet/withdraw/', {
            'amount': '100.00',
            'pin': '1234',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('minimum withdrawal', response.data['message'].lower())
        self.assertFalse(PayoutRequest.objects.filter(user=self.user).exists())

    def test_withdrawal_exactly_at_the_minimum_is_allowed(self):
        response = self.client.post('/user/customer/wallet/withdraw/', {
            'amount': '500.00',
            'pin': '1234',
        }, format='json')

        self.assertEqual(response.status_code, 200, msg=f"body: {response.data}")

    def test_deposited_funds_cannot_be_withdrawn(self):
        """Payout settings existing must not make deposits cashable out."""
        self.wallet.debit(
            Decimal('5000.00'),
            source='Spend it',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
        )
        self.wallet.credit(
            Decimal('5000.00'),
            source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        response = self.client.post('/user/customer/wallet/withdraw/', {
            'amount': '1000.00',
            'pin': '1234',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Insufficient balance', response.data['message'])
