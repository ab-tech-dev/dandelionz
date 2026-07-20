"""
Tests for paying an order from the wallet, in full or split with a card.

Two properties carry the weight here.

**Money cannot be spent twice.** The wallet is debited when checkout starts, not when the
card leg lands, so a second checkout opened in parallel must not see the same balance.

**Refunds go back to the bucket they came from.** Deposits are spendable but never
withdrawable. If cancelling a wallet-funded order credited the whole total to WITHDRAWABLE,
a customer could deposit, buy, cancel, and withdraw money that was never withdrawable - the
laundering route the two-bucket split exists to close, which only opens once checkout can
spend from SPENDABLE.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from store.models import Cart, CartItem, Product
from transactions import wallet_checkout
from transactions.models import (
    LedgerEntry,
    Order,
    Payment,
    Refund,
    Wallet,
    WalletHold,
)
from transactions.wallet_checkout import (
    SettlementBlocked as WalletHoldSettlementBlocked,
    WalletPaymentError,
    plan_split,
)
from users.models import Customer, Vendor

User = get_user_model()


class PlanSplitTests(TestCase):
    """Pure arithmetic: how an order total divides between wallet and card."""

    def test_wallet_covers_the_whole_order(self):
        self.assertEqual(
            plan_split(Decimal('1000'), Decimal('5000')),
            (Decimal('1000.00'), Decimal('0.00')),
        )

    def test_wallet_covers_part_and_the_card_takes_the_rest(self):
        self.assertEqual(
            plan_split(Decimal('5000'), Decimal('2000')),
            (Decimal('2000.00'), Decimal('3000.00')),
        )

    def test_an_empty_wallet_leaves_the_whole_total_on_the_card(self):
        self.assertEqual(
            plan_split(Decimal('5000'), Decimal('0')),
            (Decimal('0.00'), Decimal('5000.00')),
        )

    def test_a_requested_amount_is_honoured(self):
        self.assertEqual(
            plan_split(Decimal('5000'), Decimal('4000'), requested=Decimal('1000')),
            (Decimal('1000.00'), Decimal('4000.00')),
        )

    def test_a_request_larger_than_the_balance_is_refused(self):
        with self.assertRaises(WalletPaymentError):
            plan_split(Decimal('5000'), Decimal('1000'), requested=Decimal('2000'))

    def test_a_request_larger_than_the_order_is_capped_not_refused(self):
        """Asking to spend more than the order costs is not an error - it is just capped."""
        self.assertEqual(
            plan_split(Decimal('1000'), Decimal('9000'), requested=Decimal('5000')),
            (Decimal('1000.00'), Decimal('0.00')),
        )

    def test_the_card_leg_is_never_negative(self):
        wallet, card = plan_split(Decimal('100'), Decimal('99999'))
        self.assertGreaterEqual(card, Decimal('0.00'))
        self.assertEqual(wallet + card, Decimal('100.00'))


class WalletCheckoutBase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email='wc@test.com', password='pass12345', role='CUSTOMER', full_name='WC',
        )
        self.vendor_user = User.objects.create_user(
            email='wcvendor@test.com', password='pass12345', role='VENDOR',
        )
        self.profile, _ = Customer.objects.get_or_create(user=self.customer)
        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.vendor_user, defaults={'store_name': 'WC Store'},
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.customer)
        self.cart = Cart.objects.create(customer=self.customer)
        self.client.force_authenticate(user=self.customer)

        # Below the delivery threshold, so these tests exercise payment rather than shipping.
        self.product = Product.objects.create(
            store=self.vendor, name='Widget', price=Decimal('1000.00'), stock=100,
        )

    def _add_to_cart(self, quantity=1):
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=quantity)

    def _fund(self, spendable=Decimal('0'), withdrawable=Decimal('0')):
        if spendable > 0:
            self.wallet.credit(
                spendable, source='Wallet deposit',
                bucket=LedgerEntry.Bucket.SPENDABLE,
                entry_type=LedgerEntry.EntryType.DEPOSIT,
            )
        if withdrawable > 0:
            self.wallet.credit(withdrawable, source='Referral bonus')
        self.wallet.refresh_from_db()

    def _checkout(self, **body):
        return self.client.post('/transactions/checkout/', body, format='json')


@patch('transactions.tasks.notify_stakeholders_order_paid.delay')
@patch('transactions.views._notify_checkout')
@patch('transactions.views.Paystack.initialize_payment')
class SplitPaymentTests(WalletCheckoutBase):

    def test_card_only_checkout_is_unchanged(self, mock_init, _notify, _task):
        """The default body is empty, so the existing flow must behave exactly as before."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart()
        self._fund(withdrawable=Decimal('5000'))

        response = self._checkout()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['data']['requires_payment'])
        self.assertEqual(response.data['data']['wallet_amount'], 0.0)
        self.assertEqual(response.data['data']['amount'], 1000.0)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('5000.00'))
        self.assertFalse(WalletHold.objects.exists())

    def test_a_wallet_covering_the_whole_order_skips_paystack(self, mock_init, _notify, _task):
        self._add_to_cart()
        self._fund(spendable=Decimal('5000'))

        response = self._checkout(use_wallet=True)

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['data']['requires_payment'])
        self.assertIsNone(response.data['data']['authorization_url'])
        mock_init.assert_not_called()

        order = Order.objects.get(order_id=response.data['data']['order_id'])
        self.assertEqual(order.status, Order.Status.PAID)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('4000.00'))

    def test_a_fully_wallet_funded_order_captures_its_hold(self, mock_init, _notify, _task):
        """Nothing is pending, so the money is really gone and must not stay releasable."""
        self._add_to_cart()
        self._fund(spendable=Decimal('5000'))

        response = self._checkout(use_wallet=True)

        order = Order.objects.get(order_id=response.data['data']['order_id'])
        hold = WalletHold.objects.get(order=order)
        self.assertEqual(hold.status, WalletHold.Status.CAPTURED)

    def test_a_partial_balance_splits_with_the_card(self, mock_init, _notify, _task):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)  # 5000 total
        self._fund(spendable=Decimal('2000'))

        response = self._checkout(use_wallet=True)

        self.assertEqual(response.data['data']['wallet_amount'], 2000.0)
        self.assertEqual(response.data['data']['amount'], 3000.0)
        self.assertTrue(response.data['data']['requires_payment'])
        # Paystack is asked for the remainder only, never the order total.
        self.assertEqual(mock_init.call_args.kwargs['amount'], Decimal('3000.00'))

    def test_the_wallet_is_debited_before_the_card_leg_completes(self, mock_init, _notify, _task):
        """
        The balance must move at checkout, not at verification. Otherwise two checkouts
        opened together both see the same money and both succeed.
        """
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        self._fund(spendable=Decimal('2000'))

        self._checkout(use_wallet=True)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))

    def test_a_second_checkout_cannot_spend_the_held_balance(self, mock_init, _notify, _task):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        self._fund(spendable=Decimal('2000'))
        self._checkout(use_wallet=True)

        # Same balance, second attempt: the money is already held by the first order.
        self._add_to_cart(quantity=5)
        second = self._checkout(use_wallet=True)

        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data['data']['wallet_amount'], 0.0)
        self.assertEqual(second.data['data']['amount'], 5000.0)

    def test_spendable_is_consumed_before_withdrawable(self, mock_init, _notify, _task):
        """
        Deposits can only ever be spent here, so they go first. Spending the withdrawable
        half first would strand the restricted half in the wallet.
        """
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=3)  # 3000 total
        self._fund(spendable=Decimal('2000'), withdrawable=Decimal('5000'))

        self._checkout(use_wallet=True)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('4000.00'))

    def test_the_hold_records_the_split_per_bucket(self, mock_init, _notify, _task):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=3)
        self._fund(spendable=Decimal('2000'), withdrawable=Decimal('5000'))

        response = self._checkout(use_wallet=True)

        order = Order.objects.get(order_id=response.data['data']['order_id'])
        hold = WalletHold.objects.get(order=order)
        self.assertEqual(hold.spendable_amount, Decimal('2000.00'))
        self.assertEqual(hold.withdrawable_amount, Decimal('1000.00'))

    def test_an_explicit_wallet_amount_is_honoured(self, mock_init, _notify, _task):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        self._fund(withdrawable=Decimal('5000'))

        response = self._checkout(use_wallet=True, wallet_amount='1500.00')

        self.assertEqual(response.data['data']['wallet_amount'], 1500.0)
        self.assertEqual(response.data['data']['amount'], 3500.0)

    def test_asking_for_more_wallet_than_the_balance_is_refused(self, mock_init, _notify, _task):
        self._add_to_cart(quantity=5)
        self._fund(withdrawable=Decimal('1000'))

        response = self._checkout(use_wallet=True, wallet_amount='4000.00')

        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('1000.00'))

    def test_a_wallet_amount_without_use_wallet_is_refused(self, mock_init, _notify, _task):
        self._add_to_cart()
        self._fund(withdrawable=Decimal('5000'))

        response = self._checkout(wallet_amount='500.00')

        self.assertEqual(response.status_code, 400)


@patch('transactions.tasks.notify_stakeholders_order_paid.delay')
@patch('transactions.views._notify_checkout')
@patch('transactions.views.Paystack.initialize_payment')
class HoldResolutionTests(WalletCheckoutBase):

    def _split_checkout(self, mock_init):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        self._fund(spendable=Decimal('2000'))
        response = self._checkout(use_wallet=True)
        return Order.objects.get(order_id=response.data['data']['order_id'])

    def test_verifying_the_card_leg_captures_the_hold(self, mock_init, _notify, _task):
        order = self._split_checkout(mock_init)

        order.payment.mark_as_successful()

        hold = WalletHold.objects.get(order=order)
        self.assertEqual(hold.status, WalletHold.Status.CAPTURED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))

    def test_capturing_twice_does_not_move_money_again(self, mock_init, _notify, _task):
        order = self._split_checkout(mock_init)

        order.payment.mark_as_successful()
        wallet_checkout.capture_for_order(order)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))

    def test_releasing_returns_the_money_to_its_original_bucket(self, mock_init, _notify, _task):
        order = self._split_checkout(mock_init)

        wallet_checkout.release_for_order(order, reason="Card payment failed")

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('0.00'))

    def test_releasing_a_mixed_hold_restores_both_buckets_exactly(self, mock_init, _notify, _task):
        """An abandoned checkout must not quietly move money between buckets."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        # 8000 order against a 7000 wallet, so the hold spans both buckets AND a card leg
        # remains - a hold is only releasable while it is still HELD, and a wallet that
        # covers the whole total is captured at checkout instead.
        self._add_to_cart(quantity=8)
        self._fund(spendable=Decimal('2000'), withdrawable=Decimal('5000'))
        response = self._checkout(use_wallet=True)
        order = Order.objects.get(order_id=response.data['data']['order_id'])
        hold = WalletHold.objects.get(order=order)
        self.assertEqual(hold.status, WalletHold.Status.HELD)
        self.assertEqual(hold.spendable_amount, Decimal('2000.00'))
        self.assertEqual(hold.withdrawable_amount, Decimal('5000.00'))

        wallet_checkout.release_for_order(order)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('5000.00'))

    def test_releasing_twice_credits_only_once(self, mock_init, _notify, _task):
        order = self._split_checkout(mock_init)

        wallet_checkout.release_for_order(order)
        wallet_checkout.release_for_order(order)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))

    def test_a_captured_hold_cannot_then_be_released(self, mock_init, _notify, _task):
        """The money is spent; releasing it would hand back funds the order consumed."""
        order = self._split_checkout(mock_init)
        order.payment.mark_as_successful()

        wallet_checkout.release_for_order(order)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))

    def test_the_sweeper_releases_an_abandoned_hold(self, mock_init, _notify, _task):
        from django.core.management import call_command

        order = self._split_checkout(mock_init)
        hold = WalletHold.objects.get(order=order)
        hold.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        hold.save(update_fields=['expires_at'])

        call_command('release_expired_holds')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))
        hold.refresh_from_db()
        self.assertEqual(hold.status, WalletHold.Status.RELEASED)

    def test_the_sweeper_leaves_a_live_hold_alone(self, mock_init, _notify, _task):
        from django.core.management import call_command

        order = self._split_checkout(mock_init)

        call_command('release_expired_holds')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(
            WalletHold.objects.get(order=order).status, WalletHold.Status.HELD
        )


@patch('transactions.tasks.notify_stakeholders_order_paid.delay')
@patch('transactions.views._notify_checkout')
@patch('transactions.views.Paystack.initialize_payment')
class SettlementAfterReleaseTests(WalletCheckoutBase):
    """
    The double-spend the security review found.

    A split payment's two legs are separable: the wallet leg can be returned to the
    customer - by cancelling, or by the expiry sweeper - while the card leg's Paystack link
    is still live and payable. Settling then fulfils an order having collected only the
    card half, with the wallet half back in the customer's balance.

    Both variants below are fully deterministic. Neither needs a race.
    """

    def _split_order(self, mock_init):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=8)  # 8000 total
        self._fund(spendable=Decimal('5000'))
        response = self._checkout(use_wallet=True)
        return Order.objects.get(order_id=response.data['data']['order_id'])

    def test_paying_the_card_leg_after_cancelling_is_refused(self, mock_init, _notify, _task):
        """
        Cancel a PENDING split order (wallet money comes back), then pay the still-valid
        card link. Without the guard the order flips CANCELED -> PAID and ships for the
        card leg alone.
        """
        order = self._split_order(mock_init)
        self.client.post(f'/transactions/orders/{order.order_id}/cancel/')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('5000.00'))

        order.refresh_from_db()
        with self.assertRaises(WalletHoldSettlementBlocked):
            order.payment.mark_as_successful()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELED)
        self.assertFalse(order.payment.verified)

    def test_paying_after_the_sweeper_released_the_hold_is_refused(
        self, mock_init, _notify, _task
    ):
        """
        The variant that needs no cancel call at all: abandon checkout past the hold TTL,
        let release_expired_holds return the money, then pay the card leg.
        """
        from django.core.management import call_command

        order = self._split_order(mock_init)
        hold = WalletHold.objects.get(order=order)
        hold.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        hold.save(update_fields=['expires_at'])
        call_command('release_expired_holds')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('5000.00'))

        order.refresh_from_db()
        with self.assertRaises(WalletHoldSettlementBlocked):
            order.payment.mark_as_successful()

        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.Status.PAID)

    def test_a_normal_split_payment_still_settles(self, mock_init, _notify, _task):
        """The guard must not block the ordinary path it sits in front of."""
        order = self._split_order(mock_init)

        order.payment.mark_as_successful()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(
            WalletHold.objects.get(order=order).status, WalletHold.Status.CAPTURED
        )

    def test_cancelling_a_pending_order_voids_the_card_leg(self, mock_init, _notify, _task):
        """Defence in depth: the Paystack link should not be payable at all afterwards."""
        order = self._split_order(mock_init)

        self.client.post(f'/transactions/orders/{order.order_id}/cancel/')

        order.payment.refresh_from_db()
        self.assertEqual(order.payment.status, 'CANCELLED')

    def test_a_card_only_order_is_unaffected_by_the_guard(self, mock_init, _notify, _task):
        """No hold was ever placed, so there is nothing for the guard to trip on."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        response = self._checkout()
        order = Order.objects.get(order_id=response.data['data']['order_id'])

        order.payment.mark_as_successful()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)


@patch('transactions.tasks.notify_stakeholders_order_paid.delay')
@patch('transactions.views._notify_checkout')
@patch('transactions.views.Paystack.initialize_payment')
class RefundBucketTests(WalletCheckoutBase):
    """
    The laundering route this whole feature had to close.

    Deposits are spendable but never withdrawable. Refunding a wallet-funded order to
    WITHDRAWABLE would let a customer deposit, buy, cancel, and take the money to a bank.
    """

    def _paid_order(self, mock_init, spendable=Decimal('2000'),
                    withdrawable=Decimal('0'), quantity=5):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=quantity)
        self._fund(spendable=spendable, withdrawable=withdrawable)
        response = self._checkout(use_wallet=True)
        order = Order.objects.get(order_id=response.data['data']['order_id'])
        order.payment.mark_as_successful()
        return order

    def _refund(self, order, amount=None):
        wallet = Wallet.objects.get(user=self.customer)
        total = amount if amount is not None else (
            order.payment.amount + wallet_checkout.wallet_amount_paid(order)
        )
        return wallet_checkout.refund_to_source_buckets(
            wallet, order, total,
            source=f"Refund {order.payment.reference}",
            idempotency_prefix=f"order-refund-{order.payment.reference}",
            payment=order.payment,
        )

    def test_a_deposit_funded_order_refunds_to_spendable_not_withdrawable(
        self, mock_init, _notify, _task
    ):
        order = self._paid_order(mock_init, spendable=Decimal('5000'), quantity=5)

        self._refund(order)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('5000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('0.00'))

    def test_a_split_order_refunds_each_part_to_where_it_came_from(
        self, mock_init, _notify, _task
    ):
        # 5000 order: 2000 from deposits, 3000 on the card.
        order = self._paid_order(mock_init, spendable=Decimal('2000'), quantity=5)

        applied = self._refund(order)

        self.assertEqual(applied['spendable'], Decimal('2000.00'))
        self.assertEqual(applied['withdrawable'], Decimal('3000.00'))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('3000.00'))

    def test_a_card_only_order_still_refunds_to_withdrawable(self, mock_init, _notify, _task):
        """Unchanged behaviour for orders with no wallet leg."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        response = self._checkout()
        order = Order.objects.get(order_id=response.data['data']['order_id'])
        order.payment.mark_as_successful()

        applied = self._refund(order)

        self.assertEqual(applied['spendable'], Decimal('0.00'))
        self.assertEqual(applied['withdrawable'], Decimal('5000.00'))

    def test_a_partial_refund_is_allocated_proportionally(
        self, mock_init, _notify, _task
    ):
        """
        A ₦5,000 order paid ₦2,000 wallet / ₦3,000 card is 40% wallet-funded, so a ₦1,000
        partial refund returns ₦400 spendable and ₦600 withdrawable.

        Returning the wallet share first instead would be safer for the platform but wrong
        for the customer: on an order paid mostly by card they would get back spend-only
        money for a purchase they largely paid for with a card.
        """
        order = self._paid_order(mock_init, spendable=Decimal('2000'), quantity=5)

        applied = self._refund(order, amount=Decimal('1000.00'))

        self.assertEqual(applied['spendable'], Decimal('400.00'))
        self.assertEqual(applied['withdrawable'], Decimal('600.00'))

    def test_a_partial_refund_never_returns_more_spendable_than_was_paid(
        self, mock_init, _notify, _task
    ):
        """The proportional share is still capped by what the wallet actually put in."""
        order = self._paid_order(mock_init, spendable=Decimal('2000'), quantity=5)

        applied = self._refund(order, amount=Decimal('5000.00'))

        self.assertEqual(applied['spendable'], Decimal('2000.00'))
        self.assertEqual(applied['withdrawable'], Decimal('3000.00'))

    def test_cancelling_refunds_the_wallet_leg_as_well_as_the_card(
        self, mock_init, _notify, _task
    ):
        """
        payment.amount is only the card portion of a split payment. Refunding that alone
        would silently keep whatever the customer paid from their wallet.
        """
        order = self._paid_order(mock_init, spendable=Decimal('2000'), quantity=5)

        response = self.client.post(f'/transactions/orders/{order.order_id}/cancel/')

        self.assertIn(response.status_code, (200, 201))
        refund = Refund.objects.get(payment=order.payment)
        self.assertEqual(refund.refunded_amount, Decimal('5000.00'))

    def test_cancelling_an_unpaid_order_releases_its_hold(self, mock_init, _notify, _task):
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        self._add_to_cart(quantity=5)
        self._fund(spendable=Decimal('2000'))
        response = self._checkout(use_wallet=True)
        order = Order.objects.get(order_id=response.data['data']['order_id'])

        self.client.post(f'/transactions/orders/{order.order_id}/cancel/')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))
