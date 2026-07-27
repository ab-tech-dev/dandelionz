"""
Layered platform commission: product override -> vendor rate -> platform default, capped.

These pin the rules the money paths depend on - that the resolver picks the most specific
rate, never exceeds the ceiling, and that a refund reverses exactly what was credited even
if the rate was changed in between (the reversal reads the ledger, not the current rate).
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from store.models import Product
from transactions import commission
from transactions.commission import resolve_commission_rate, vendor_share_rate
from transactions.models import LedgerEntry, Order, OrderItem, Wallet
from users.models import Customer, Vendor

User = get_user_model()


class CommissionResolverTests(TestCase):
    def setUp(self):
        self.vendor_user = User.objects.create_user(
            email='cv@test.com', password='pass12345', role='VENDOR',
        )
        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.vendor_user, defaults={'store_name': 'CV Store'},
        )
        self.product = Product.objects.create(
            store=self.vendor, name='Widget', price=Decimal('1000.00'), stock=10,
        )

    def test_default_rate_when_nothing_set(self):
        self.assertEqual(resolve_commission_rate(product=self.product), Decimal('0.10'))
        self.assertEqual(vendor_share_rate(product=self.product), Decimal('0.90'))

    def test_vendor_rate_beats_default(self):
        self.vendor.commission_rate = Decimal('0.08')
        self.vendor.save()
        self.product.refresh_from_db()
        self.assertEqual(resolve_commission_rate(product=self.product), Decimal('0.08'))

    def test_product_override_beats_vendor(self):
        self.vendor.commission_rate = Decimal('0.08')
        self.vendor.save()
        self.product.commission_rate = Decimal('0.05')
        self.product.save()
        self.assertEqual(resolve_commission_rate(product=self.product), Decimal('0.05'))

    def test_zero_rate_is_honoured_not_treated_as_unset(self):
        # 0% is a real, deliberate rate (free selling); it must not fall through to 10%.
        self.product.commission_rate = Decimal('0.000')
        self.product.save()
        self.assertEqual(resolve_commission_rate(product=self.product), Decimal('0'))

    def test_rate_is_clamped_to_ceiling(self):
        # A DB value above the ceiling (bypassing validators) is still capped by the resolver.
        self.vendor.commission_rate = Decimal('0.99')
        self.vendor.save()
        self.assertEqual(resolve_commission_rate(product=self.product), commission.MAX_COMMISSION_RATE)

    def test_resolve_from_order_item(self):
        self.product.commission_rate = Decimal('0.06')
        self.product.save()
        customer = User.objects.create_user(
            email='cc@test.com', password='pass12345', role='CUSTOMER',
        )
        Customer.objects.get_or_create(user=customer)
        order = Order.objects.create(customer=customer, total_price=Decimal('2000.00'))
        item = OrderItem.objects.create(
            order=order, product=self.product, quantity=2, price_at_purchase=Decimal('1000.00'),
        )
        self.assertEqual(resolve_commission_rate(item), Decimal('0.06'))

    def test_format_rate_label(self):
        self.assertEqual(commission.format_rate_label(Decimal('0.10')), '10%')
        self.assertEqual(commission.format_rate_label(Decimal('0.08')), '8%')
        self.assertEqual(commission.format_rate_label(Decimal('0.075')), '7.5%')


@patch('transactions.views._notify_checkout', lambda *a, **k: None)
class CommissionCreditAndReversalTests(TestCase):
    """The credit uses the resolved rate; the reversal undoes exactly what the ledger recorded."""

    def setUp(self):
        self.vendor_user = User.objects.create_user(
            email='rv@test.com', password='pass12345', role='VENDOR',
        )
        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.vendor_user, defaults={'store_name': 'RV Store'},
        )
        self.product = Product.objects.create(
            store=self.vendor, name='Gadget', price=Decimal('1000.00'), stock=10,
        )
        self.customer = User.objects.create_user(
            email='rc@test.com', password='pass12345', role='CUSTOMER',
        )
        Customer.objects.get_or_create(user=self.customer)
        # credit_vendors_for_order only records platform commission when a business-admin
        # wallet exists to receive it - create one so the commission ledger entry is written.
        self.admin = User.objects.create_user(
            email='biz@test.com', password='pass12345', role=User.Role.BUSINESS_ADMIN,
        )

    def _delivered_order(self, rate):
        self.vendor.commission_rate = rate
        self.vendor.save()
        order = Order.objects.create(
            customer=self.customer, total_price=Decimal('5000.00'),
            status=Order.Status.DELIVERED,
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=5, price_at_purchase=Decimal('1000.00'),
        )
        return order

    def test_credit_uses_resolved_rate(self):
        from transactions.views import credit_vendors_for_order
        from django.db import transaction

        order = self._delivered_order(Decimal('0.08'))  # 8% of 5000 = 400 commission
        with transaction.atomic():
            credit_vendors_for_order(order)

        vendor_wallet = Wallet.objects.get(user=self.vendor_user)
        # Vendor gets 92% of 5000 = 4600
        self.assertEqual(vendor_wallet.withdrawable_balance, Decimal('4600.00'))
        commission_entry = LedgerEntry.objects.get(
            idempotency_key=f"commission-{order.order_id}-{order.order_items.first().id}",
        )
        self.assertEqual(commission_entry.amount, Decimal('400.00'))

    def test_reversal_reads_the_ledger_even_after_the_rate_changes(self):
        from transactions.views import credit_vendors_for_order
        from django.db import transaction

        order = self._delivered_order(Decimal('0.08'))  # credited at 8% -> 400 commission
        with transaction.atomic():
            credit_vendors_for_order(order)
            order.vendors_credited = True
            order.save(update_fields=['vendors_credited'])

        # The rate is changed AFTER crediting. A recompute would reverse 5000*0.10=500, wrong.
        self.vendor.commission_rate = Decimal('0.10')
        self.vendor.save()

        item = order.order_items.first()
        credited = LedgerEntry.objects.get(
            idempotency_key=f"commission-{order.order_id}-{item.id}",
        )
        self.assertEqual(credited.amount, Decimal('400.00'))  # the true charge, not 500


class AdminSetCommissionEndpointTests(TestCase):
    """The admin endpoints that set/clear per-vendor and per-product commission rates."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@test.com', password='pass12345', role=User.Role.BUSINESS_ADMIN,
        )
        self.vendor_user = User.objects.create_user(
            email='ev@test.com', password='pass12345', role='VENDOR',
        )
        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.vendor_user, defaults={'store_name': 'EV Store'},
        )
        self.product = Product.objects.create(
            store=self.vendor, name='Thing', price=Decimal('1000.00'), stock=10,
        )
        self.client.force_authenticate(user=self.admin)

    def _vendor_url(self):
        return reverse('admin-set-vendor-commission', kwargs={'vendor_uuid': self.vendor_user.uuid})

    def _product_url(self):
        return reverse('admin-set-product-commission', kwargs={'slug': self.product.slug})

    def test_admin_sets_vendor_rate(self):
        resp = self.client.patch(self._vendor_url(), {'commission_rate': '0.07'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.commission_rate, Decimal('0.070'))

    def test_admin_clears_vendor_rate_with_null(self):
        self.vendor.commission_rate = Decimal('0.05')
        self.vendor.save()
        resp = self.client.patch(self._vendor_url(), {'commission_rate': None}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.vendor.refresh_from_db()
        self.assertIsNone(self.vendor.commission_rate)

    def test_admin_sets_product_rate(self):
        resp = self.client.patch(self._product_url(), {'commission_rate': '0.04'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.commission_rate, Decimal('0.040'))
        self.assertEqual(resp.data['data']['effective_rate_label'], '4%')

    def test_rate_above_ceiling_is_rejected(self):
        resp = self.client.patch(self._vendor_url(), {'commission_rate': '0.20'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.vendor.refresh_from_db()
        self.assertIsNone(self.vendor.commission_rate)

    def test_non_admin_is_forbidden(self):
        self.client.force_authenticate(user=self.vendor_user)
        resp = self.client.patch(self._vendor_url(), {'commission_rate': '0.05'}, format='json')
        self.assertEqual(resp.status_code, 403)
        self.vendor.refresh_from_db()
        self.assertIsNone(self.vendor.commission_rate)
