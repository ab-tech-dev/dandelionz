"""
Tests for account closure guards and anonymisation.

The behaviour being protected: a user must not be able to close their account while money
is still in their wallet, and closing must not destroy the ledger.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from transactions.models import LedgerEntry, Wallet, WalletHold
from django.utils import timezone
from users.models import PayoutRequest
from users.services.account_closure import (
    BLOCKED_ACTIVE_HOLD,
    BLOCKED_PENDING_WITHDRAWAL,
    BLOCKED_SPENDABLE,
    BLOCKED_WITHDRAWABLE,
    check_can_close,
    close_account,
)

User = get_user_model()


class AccountClosureGuardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='closing@test.com', password='test123', full_name='Closing User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_empty_wallet_can_close(self):
        allowed, blocker = check_can_close(self.user)

        self.assertTrue(allowed)
        self.assertIsNone(blocker)

    def test_withdrawable_balance_blocks_closure_and_says_to_withdraw(self):
        self.wallet.credit(Decimal('4500.00'), source='Refund')

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_WITHDRAWABLE)
        self.assertIn('Withdraw it to your bank', blocker['message'])
        self.assertIn('4,500.00', blocker['message'])

    def test_deposited_balance_blocks_closure_and_does_not_offer_a_bank_withdrawal(self):
        """
        Deposits must never be routed to a bank, and account closure is the most
        attractive moment to try it - the message must not suggest that route.
        """
        self.wallet.credit(
            Decimal('2000.00'),
            source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_SPENDABLE)
        self.assertIn('refund to your original payment card', blocker['message'])
        self.assertNotIn('Withdraw it to your bank', blocker['message'])

    def test_withdrawable_is_reported_before_spendable(self):
        """With both, the actionable one the user can resolve themselves comes first."""
        self.wallet.credit(Decimal('100.00'), source='Refund')
        self.wallet.credit(
            Decimal('100.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_WITHDRAWABLE)

    def test_live_wallet_hold_blocks_closure(self):
        """An in-flight checkout is holding funds that are not yet spent or released."""
        WalletHold.objects.create(
            wallet=self.wallet,
            reference='HOLD-CLOSE-1',
            amount=Decimal('300.00'),
            spendable_amount=Decimal('300.00'),
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_ACTIVE_HOLD)

    def test_released_hold_does_not_block_closure(self):
        hold = WalletHold.objects.create(
            wallet=self.wallet,
            reference='HOLD-CLOSE-2',
            amount=Decimal('300.00'),
            status=WalletHold.Status.RELEASED,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        allowed, _ = check_can_close(self.user)

        self.assertTrue(allowed)

    def test_pending_withdrawal_blocks_closure(self):
        """Money already on its way out still belongs to them until it lands or fails."""
        PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            account_name='Closing User',
            reference='WTH-CLOSING1',
            status='pending',
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_PENDING_WITHDRAWAL)

    def test_completed_withdrawal_does_not_block_closure(self):
        PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            account_name='Closing User',
            reference='WTH-CLOSING2',
            status='successful',
        )

        allowed, _ = check_can_close(self.user)

        self.assertTrue(allowed)


class AccountAnonymisationTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='anon@test.com', password='test123', full_name='Anon User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('500.00'), source='Refund')
        self.wallet.debit(
            Decimal('500.00'),
            source='Withdrawal WTH-X',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
        )

    def test_closing_keeps_the_ledger_intact(self):
        """The whole point of anonymising rather than deleting."""
        entry_count = LedgerEntry.objects.filter(wallet=self.wallet).count()

        close_account(self.user)

        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), entry_count)

    def test_closing_removes_identifying_data(self):
        close_account(self.user)

        self.user.refresh_from_db()
        self.assertNotIn('anon@test.com', self.user.email)
        self.assertTrue(self.user.email.endswith('@removed.invalid'))
        self.assertEqual(self.user.full_name, 'Closed Account')
        self.assertFalse(self.user.is_active)

    def test_closed_account_cannot_log_in_with_the_old_password(self):
        close_account(self.user)

        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('test123'))
        self.assertFalse(self.user.has_usable_password())

    def test_two_closed_accounts_do_not_collide_on_email(self):
        other = User.objects.create_user(
            email='anon2@test.com', password='test123', full_name='Anon Two',
        )

        close_account(self.user)
        close_account(other)

        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertNotEqual(self.user.email, other.email)

    def test_the_original_email_can_be_reused_after_closure(self):
        """Someone closing their account should be able to sign up again later."""
        close_account(self.user)

        reused = User.objects.create_user(
            email='anon@test.com', password='new123', full_name='Returning User',
        )
        self.assertEqual(reused.email, 'anon@test.com')


class ProfileScrubbingTests(TestCase):
    """
    Anonymising the user row is not enough on its own: bank details and addresses live on
    the role profiles, and leaving them behind means a closed account still holds the most
    sensitive data we store. The ledger references none of it and PayoutRequest keeps its
    own snapshot of the destination account, so clearing it costs the audit trail nothing.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='scrub@test.com', password='test123', full_name='Scrub User',
        )
        Wallet.objects.get_or_create(user=self.user)

    def _customer_with_details(self):
        from users.models import Customer

        customer, _ = Customer.objects.get_or_create(user=self.user)
        customer.shipping_address = '12 Allen Avenue'
        customer.city = 'Ikeja'
        customer.postal_code = '100001'
        customer.bank_name = 'Test Bank'
        customer.bank_code = '058'
        customer.account_number = '0123456789'
        customer.account_name = 'Scrub User'
        customer.recipient_code = 'RCP_test123'
        customer.save()
        # The reverse OneToOne is cached on the user, so re-fetch or close_account would
        # scrub a different instance than the one asserted on.
        self.user = User.objects.get(pk=self.user.pk)
        return customer

    def test_closing_clears_customer_bank_details(self):
        self._customer_with_details()

        close_account(self.user)

        customer = User.objects.get(pk=self.user.pk).customer_profile
        self.assertEqual(customer.bank_name, '')
        self.assertEqual(customer.bank_code, '')
        self.assertEqual(customer.account_number, '')
        self.assertEqual(customer.account_name, '')
        self.assertEqual(customer.recipient_code, '')

    def test_closing_clears_customer_address(self):
        self._customer_with_details()

        close_account(self.user)

        customer = User.objects.get(pk=self.user.pk).customer_profile
        self.assertEqual(customer.shipping_address, '')
        self.assertEqual(customer.city, '')
        self.assertEqual(customer.postal_code, '')

    def test_closing_clears_vendor_bank_details(self):
        from users.models import Vendor

        vendor_user = User.objects.create_user(
            email='scrubvendor@test.com', password='test123', full_name='Scrub Vendor',
        )
        Wallet.objects.get_or_create(user=vendor_user)
        vendor, _ = Vendor.objects.get_or_create(user=vendor_user)
        vendor.bank_name = 'Test Bank'
        vendor.bank_code = '058'
        vendor.account_number = '0123456789'
        vendor.recipient_code = 'RCP_vendor'
        vendor.address = '9 Store Road'
        vendor.save()
        vendor_user = User.objects.get(pk=vendor_user.pk)

        close_account(vendor_user)

        vendor.refresh_from_db()
        self.assertEqual(vendor.bank_code, '')
        self.assertEqual(vendor.account_number, '')
        self.assertEqual(vendor.recipient_code, '')
        self.assertEqual(vendor.address, '')

    def test_closing_deletes_the_payment_pin(self):
        from users.models import PaymentPIN

        pin = PaymentPIN(user=self.user)
        pin.set_pin('1234')

        close_account(self.user)

        self.assertFalse(PaymentPIN.objects.filter(user=self.user).exists())

    def test_closing_keeps_the_payout_history(self):
        """
        The destination account is retained on PayoutRequest, not on the profile: that is
        the record of where money actually went, and it has to survive closure.
        """
        self._customer_with_details()
        payout = PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='Test Bank',
            account_number='0123456789',
            reference='WTH-KEEPME',
            status='completed',
            processed_at=timezone.now(),
        )

        close_account(self.user)

        payout.refresh_from_db()
        self.assertEqual(payout.account_number, '0123456789')
        self.assertEqual(payout.amount, Decimal('1000.00'))

    def test_closing_works_for_a_user_with_no_profile(self):
        """A user with no role profile must not trip the scrubber."""
        close_account(self.user)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_closing_clears_vendor_store_coordinates(self):
        """
        The store location is often a sole trader's home. Clearing the address text while
        keeping metre-accurate coordinates would leave the more identifying half behind.
        """
        from users.models import Vendor

        vendor_user = User.objects.create_user(
            email='coords@test.com', password='test123', full_name='Coords Vendor',
        )
        Wallet.objects.get_or_create(user=vendor_user)
        vendor, _ = Vendor.objects.get_or_create(user=vendor_user)
        vendor.address = '9 Store Road'
        vendor.store_latitude = 6.5244
        vendor.store_longitude = 3.3792
        vendor.save()

        close_account(User.objects.get(pk=vendor_user.pk))

        vendor.refresh_from_db()
        self.assertIsNone(vendor.store_latitude)
        self.assertIsNone(vendor.store_longitude)


class ClosureEndpointGuardTests(TestCase):
    """
    Both closure routes must enforce the balance guard.

    There are two per role - DELETE /user/customer/account/ and POST
    .../delete_account/ - and the DELETE route used to only flip is_active. A customer
    holding a balance could close there, lose access, and strand the money, which defeated
    the guard entirely since either endpoint is reachable from a client.
    """

    def setUp(self):
        from users.models import Customer

        self.user = User.objects.create_user(
            email='endpoint@test.com', password='test123', full_name='Endpoint User',
        )
        Customer.objects.get_or_create(user=self.user)
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_delete_route_refuses_while_funds_remain(self):
        self.wallet.credit(Decimal('7500.00'), source='Refund')

        response = self.client.delete(
            '/user/customer/account/', {'password': 'test123'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['reason'], BLOCKED_WITHDRAWABLE)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_delete_route_refuses_while_deposits_remain(self):
        self.wallet.credit(
            Decimal('2000.00'),
            source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        response = self.client.delete(
            '/user/customer/account/', {'password': 'test123'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['reason'], BLOCKED_SPENDABLE)

    def test_delete_route_anonymises_an_empty_account(self):
        response = self.client.delete(
            '/user/customer/account/', {'password': 'test123'}, format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        # The old route only flipped is_active and left every identifying field in place.
        self.assertTrue(self.user.email.endswith('@removed.invalid'))
        self.assertEqual(self.user.full_name, 'Closed Account')

    def test_delete_route_still_requires_the_password(self):
        response = self.client.delete(
            '/user/customer/account/', {'password': 'wrong'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)


class VendorStoreClosureTests(TestCase):
    """
    A closed vendor's products must come off sale. Their address is scrubbed on the way
    out, and a published product whose vendor has neither an address nor coordinates fails
    geocoding at checkout - the customer gets an unactionable shipping-fee error instead of
    simply not seeing the item.
    """

    def setUp(self):
        from users.models import Vendor

        self.user = User.objects.create_user(
            email='store@test.com', password='test123', full_name='Store Vendor',
        )
        Wallet.objects.get_or_create(user=self.user)
        self.vendor, _ = Vendor.objects.get_or_create(user=self.user)
        self.user = User.objects.get(pk=self.user.pk)

    def test_closing_takes_the_vendors_products_off_sale(self):
        from store.models import Product

        product = Product.objects.create(
            store=self.vendor,
            name='Test Product',
            price=Decimal('1000.00'),
            publish_status='published',
        )

        close_account(self.user)

        product.refresh_from_db()
        self.assertEqual(product.publish_status, 'draft')
