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
        self.assertIn('original payment card', blocker['message'])
        self.assertNotIn('Withdraw it to your bank', blocker['message'])
        # The message names a route the user can actually take.
        self.assertEqual(blocker['refund_endpoint'], '/transactions/wallet/deposit/refund/')

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


class AccountClosureOrderGuardTests(TestCase):
    """A closure must not strand money or fulfilment that is already in motion."""

    def setUp(self):
        from users.models import Customer

        self.user = User.objects.create_user(
            email='buyer@test.com', password='test123', full_name='Buyer',
        )
        Customer.objects.get_or_create(user=self.user)
        Wallet.objects.get_or_create(user=self.user)

    def _order(self, status):
        from transactions.models import Order

        return Order.objects.create(customer=self.user, status=status)

    def test_paid_undelivered_order_blocks_closure(self):
        from transactions.models import Order

        self._order(Order.Status.PAID)
        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], 'open_order')
        self.assertIn('Cancel it', blocker['message'])

    def test_shipped_order_blocks_closure(self):
        from transactions.models import Order

        self._order(Order.Status.SHIPPED)
        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], 'open_order')
        self.assertIn('on its way', blocker['message'])

    def test_unpaid_order_does_not_block_and_is_cancelled_on_closure(self):
        from transactions.models import Order, OrderStatusHistory, Payment

        order = self._order(Order.Status.PENDING)
        payment = Payment.objects.create(order=order, amount=Decimal('100.00'))

        allowed, _ = check_can_close(self.user)
        self.assertTrue(allowed)

        close_account(self.user)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELED)
        self.assertEqual(payment.status, 'CANCELLED')
        self.assertTrue(
            OrderStatusHistory.objects.filter(order=order, status=Order.Status.CANCELED).exists()
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_paid_order_is_left_alone_when_closure_is_refused(self):
        from transactions.models import Order
        from users.services.account_closure import AccountClosureBlocked

        pending = self._order(Order.Status.PENDING)
        self._order(Order.Status.PAID)

        with self.assertRaises(AccountClosureBlocked):
            close_account(self.user)

        pending.refresh_from_db()
        self.assertEqual(pending.status, Order.Status.PENDING)

    def test_pending_refund_blocks_closure(self):
        from transactions.models import Order, Payment, Refund

        order = self._order(Order.Status.CANCELED)
        payment = Payment.objects.create(order=order, amount=Decimal('100.00'), verified=True)
        Refund.objects.create(payment=payment, refunded_amount=Decimal('100.00'))

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], 'pending_refund')

    def test_processed_refund_does_not_block_closure(self):
        from transactions.models import Order, Payment, Refund

        order = self._order(Order.Status.CANCELED)
        payment = Payment.objects.create(order=order, amount=Decimal('100.00'), verified=True)
        Refund.objects.create(
            payment=payment, refunded_amount=Decimal('100.00'), status=Refund.Status.APPROVED,
        )

        allowed, _ = check_can_close(self.user)

        self.assertTrue(allowed)

    def test_card_refund_in_flight_blocks_closure(self):
        from transactions.models import Order, OrderPaymentRefund, Payment

        order = self._order(Order.Status.CANCELED)
        payment = Payment.objects.create(order=order, amount=Decimal('100.00'), verified=True)
        OrderPaymentRefund.objects.create(
            payment=payment, order=order, reference='ref-1', amount=Decimal('100.00'),
            status=OrderPaymentRefund.Status.PROCESSING,
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], 'pending_refund')

    def test_delivered_and_cancelled_orders_do_not_block(self):
        from transactions.models import Order

        self._order(Order.Status.DELIVERED)
        self._order(Order.Status.CANCELED)
        allowed, _ = check_can_close(self.user)

        self.assertTrue(allowed)

    def test_close_account_refuses_with_an_open_order_and_leaves_the_account_alone(self):
        from transactions.models import Order

        self._order(Order.Status.PAID)
        from users.services.account_closure import AccountClosureBlocked

        with self.assertRaises(AccountClosureBlocked):
            close_account(self.user)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.email, 'buyer@test.com')

    def test_blocked_error_body_carries_the_keys_the_clients_read(self):
        from users.services.account_closure import AccountClosureBlocked

        err = AccountClosureBlocked({'reason': 'open_order', 'message': 'Wait.', 'amount': None})

        self.assertEqual(err.status_code, 400)
        for key in ('error', 'message', 'detail', 'reason'):
            self.assertEqual(str(err.detail[key]), 'Wait.' if key != 'reason' else 'open_order')
        self.assertNotIn('amount', err.detail)


class VendorClosureTests(TestCase):
    """What a vendor closing leaves behind for admins and customers."""

    def setUp(self):
        from store.models import Product
        from users.models import Customer, Vendor

        self.vendor_user = User.objects.create_user(
            email='shop@test.com', password='test123', full_name='Shop',
        )
        Wallet.objects.get_or_create(user=self.vendor_user)
        self.vendor, _ = Vendor.objects.get_or_create(user=self.vendor_user)
        self.product = Product.objects.create(
            store=self.vendor, name='Lamp', slug='lamp', price=Decimal('5000.00'), stock=5,
            publish_status='submitted', approval_status='approved',
        )
        self.buyer = User.objects.create_user(
            email='shopper@test.com', password='test123', full_name='Shopper',
        )
        Customer.objects.get_or_create(user=self.buyer)

    def test_paid_order_for_the_vendors_product_blocks_closure(self):
        from transactions.models import Order, OrderItem

        order = Order.objects.create(customer=self.buyer, status=Order.Status.PAID)
        OrderItem.objects.create(order=order, product=self.product, quantity=1)

        allowed, blocker = check_can_close(self.vendor_user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], 'vendor_open_order')

    def test_delivered_order_does_not_block_closure(self):
        from transactions.models import Order, OrderItem

        order = Order.objects.create(customer=self.buyer, status=Order.Status.DELIVERED)
        OrderItem.objects.create(order=order, product=self.product, quantity=1)

        allowed, _ = check_can_close(self.vendor_user)

        self.assertTrue(allowed)

    def test_closing_removes_the_product_from_carts_and_favourites(self):
        from store.models import Cart, CartItem, Favourite

        cart, _ = Cart.objects.get_or_create(customer=self.buyer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        Favourite.objects.create(customer=self.buyer, product=self.product)

        close_account(self.vendor_user)

        self.assertFalse(CartItem.objects.filter(product=self.product).exists())
        self.assertFalse(Favourite.objects.filter(product=self.product).exists())

    def test_closed_vendors_products_are_hidden_from_the_admin_queryset(self):
        from store.models import Product
        from users.services.account_closure import exclude_closed_vendors

        close_account(self.vendor_user)

        self.assertEqual(Product.objects.filter(slug='lamp').count(), 1)
        self.assertFalse(exclude_closed_vendors(Product.objects.all()).filter(slug='lamp').exists())

    def test_suspended_vendors_products_stay_visible_to_admins(self):
        from store.models import Product
        from users.services.account_closure import exclude_closed_vendors

        self.vendor_user.is_active = False
        self.vendor_user.save(update_fields=['is_active'])

        self.assertTrue(exclude_closed_vendors(Product.objects.all()).filter(slug='lamp').exists())

    def test_admin_cannot_approve_a_closed_vendors_product(self):
        close_account(self.vendor_user)
        admin = User.objects.create_user(
            email='root@test.com', password='test123', full_name='Root', role='ADMIN',
            is_staff=True, is_superuser=True,
        )

        from store.views import ApproveProductView

        view = ApproveProductView.as_view()
        from rest_framework.test import APIRequestFactory, force_authenticate

        request = APIRequestFactory().post('/x/', {}, format='json')
        force_authenticate(request, user=admin)
        response = view(request, slug='lamp')

        self.assertEqual(response.status_code, 404)

    def test_public_detail_and_cart_refuse_a_draft_product(self):
        from store.models import Product
        from store.views import AddToCartView, ProductDetailView
        from rest_framework.test import APIRequestFactory, force_authenticate

        Product.objects.filter(pk=self.product.pk).update(publish_status='draft')
        factory = APIRequestFactory()

        detail = ProductDetailView.as_view()(factory.get('/x/'), slug='lamp')
        self.assertEqual(detail.status_code, 404)

        request = factory.post('/x/', {'slug': 'lamp', 'quantity': 1}, format='json')
        force_authenticate(request, user=self.buyer)
        added = AddToCartView.as_view()(request)
        self.assertIn(added.status_code, (400, 404))
        from store.models import CartItem
        self.assertFalse(CartItem.objects.filter(product=self.product).exists())

    def test_vendor_can_still_open_their_own_draft(self):
        from store.models import Product
        from store.views import ProductDetailView
        from rest_framework.test import APIRequestFactory, force_authenticate

        Product.objects.filter(pk=self.product.pk).update(publish_status='draft')
        request = APIRequestFactory().get('/x/')
        force_authenticate(request, user=self.vendor_user)

        response = ProductDetailView.as_view()(request, slug='lamp')

        self.assertEqual(response.status_code, 200)

    def test_logged_in_customer_cannot_open_a_draft_product(self):
        from store.models import Product
        from store.views import ProductDetailView
        from rest_framework.test import APIRequestFactory, force_authenticate

        Product.objects.filter(pk=self.product.pk).update(publish_status='draft')
        request = APIRequestFactory().get('/x/')
        force_authenticate(request, user=self.buyer)

        self.assertEqual(ProductDetailView.as_view()(request, slug='lamp').status_code, 404)

    def test_another_vendor_cannot_open_this_vendors_draft(self):
        from store.models import Product
        from store.views import ProductDetailView
        from rest_framework.test import APIRequestFactory, force_authenticate
        from users.models import Vendor

        Product.objects.filter(pk=self.product.pk).update(publish_status='draft')
        other = User.objects.create_user(
            email='rival@test.com', password='test123', full_name='Rival', role='VENDOR',
        )
        Vendor.objects.get_or_create(user=other)
        request = APIRequestFactory().get('/x/')
        force_authenticate(request, user=other)

        self.assertEqual(ProductDetailView.as_view()(request, slug='lamp').status_code, 404)

    def test_admin_and_business_admin_can_open_a_pending_product(self):
        from store.models import Product
        from store.views import ProductDetailView
        from rest_framework.test import APIRequestFactory, force_authenticate

        Product.objects.filter(pk=self.product.pk).update(
            publish_status='submitted', approval_status='pending',
        )
        for role in ('ADMIN', 'BUSINESS_ADMIN'):
            staff = User.objects.create_user(
                email=f'{role.lower()}@test.com', password='test123', full_name=role, role=role,
            )
            request = APIRequestFactory().get('/x/')
            force_authenticate(request, user=staff)
            self.assertEqual(
                ProductDetailView.as_view()(request, slug='lamp').status_code, 200, role,
            )

    def test_listed_product_is_visible_to_everyone(self):
        from store.views import ProductDetailView
        from rest_framework.test import APIRequestFactory

        response = ProductDetailView.as_view()(APIRequestFactory().get('/x/'), slug='lamp')

        self.assertEqual(response.status_code, 200)
