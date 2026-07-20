"""
Recommendation engine tests.

These are mostly *contracts* about ranking and fallback: a related product must
outrank an unrelated one, and every entry point must still return something
useful on a store with no interaction history at all. The cold-start paths get
as much coverage as the personalized ones because a young catalogue is the
normal case, not the edge case.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from transactions.models import Order, OrderItem
from users.models import Vendor
from .models import Category, Favourite, InteractionEvent, Product
from .recommendations import (
    MAX_LIMIT,
    clamp_limit,
    personalized_products,
    related_products,
    trending_products,
)


def _make_vendor(email='vendor@example.com', store_name='Test Shop'):
    """
    A post_save signal already creates a Vendor for VENDOR users, so reuse that
    row rather than creating a second one and tripping the unique constraint.
    """
    User = get_user_model()
    user = User.objects.create_user(email=email, password='pass123', role='VENDOR')
    vendor = Vendor.objects.filter(user=user).first()
    if vendor is None:
        vendor = Vendor.objects.create(user=user, store_name=store_name, is_verified_vendor=True)
    return vendor


class RecommendationTestBase(TestCase):
    """Shared catalogue helpers. Cache is cleared because trending is cached."""

    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()
        self.shoes = Category.objects.create(name='Footwear')
        self.kitchen = Category.objects.create(name='Kitchen')

    def _product(self, name, **kwargs):
        kwargs.setdefault('price', '100.00')
        kwargs.setdefault('stock', 5)
        kwargs.setdefault('approval_status', 'approved')
        kwargs.setdefault('publish_status', 'submitted')
        return Product.objects.create(store=self.vendor, name=name, **kwargs)

    def _customer(self, email='cust@example.com'):
        User = get_user_model()
        return User.objects.create_user(email=email, password='pass123')

    def _purchase(self, customer, *products):
        order = Order.objects.create(customer=customer, status=Order.Status.PAID)
        for product in products:
            OrderItem.objects.create(order=order, product=product, quantity=1, price_at_purchase=product.price)
        return order


class RelatedProductsTests(RecommendationTestBase):
    def test_same_category_outranks_unrelated(self):
        seed = self._product('Running Shoe', category=self.shoes)
        sibling = self._product('Trail Shoe', category=self.shoes)
        unrelated = self._product('Frying Pan', category=self.kitchen)

        results = related_products(seed, limit=8)

        self.assertEqual(results[0], sibling)
        self.assertNotIn(unrelated, results)

    def test_tag_overlap_outranks_category_alone(self):
        seed = self._product('Running Shoe', category=self.shoes, tags='waterproof,trail')
        tagged = self._product('Hiking Boot', category=self.kitchen, tags='waterproof,trail')
        category_only = self._product('Dress Shoe', category=self.shoes)

        results = related_products(seed, limit=8)

        self.assertEqual(results[0], tagged)
        self.assertIn(category_only, results)

    def test_same_brand_is_related(self):
        seed = self._product('Mystery Item', brand='Umbro')
        same_brand = self._product('Other Item', brand='Umbro')

        self.assertIn(same_brand, related_products(seed, limit=8))

    def test_similar_price_breaks_tie_within_category(self):
        seed = self._product('Running Shoe', category=self.shoes, price='100.00')
        close = self._product('Trail Shoe', category=self.shoes, price='105.00')
        far = self._product('Luxury Shoe', category=self.shoes, price='900.00')

        results = related_products(seed, limit=8)

        self.assertEqual(results[0], close)
        self.assertIn(far, results)

    def test_seed_product_is_excluded(self):
        seed = self._product('Running Shoe', category=self.shoes)
        self._product('Trail Shoe', category=self.shoes)

        self.assertNotIn(seed, related_products(seed, limit=8))

    def test_unapproved_products_are_excluded(self):
        seed = self._product('Running Shoe', category=self.shoes)
        hidden = self._product('Secret Shoe', category=self.shoes, approval_status='pending')

        self.assertNotIn(hidden, related_products(seed, limit=8))

    def test_falls_back_to_trending_when_nothing_matches(self):
        """A lone product must not produce an empty carousel."""
        seed = self._product('Running Shoe', category=self.shoes)
        other = self._product('Frying Pan', category=self.kitchen)

        results = related_products(seed, limit=8)

        self.assertEqual(results, [other])


class TrendingProductsTests(RecommendationTestBase):
    def test_works_with_no_personalization_data(self):
        """Cold start: no orders, no reviews, no events -- still returns products."""
        self._product('Running Shoe', category=self.shoes)
        self._product('Frying Pan', category=self.kitchen)

        self.assertEqual(len(trending_products(limit=8)), 2)

    def test_recent_orders_outrank_no_orders(self):
        popular = self._product('Running Shoe', category=self.shoes)
        ignored = self._product('Frying Pan', category=self.kitchen)
        customer = self._customer()
        self._purchase(customer, popular)

        results = trending_products(limit=8)

        self.assertEqual(results[0], popular)
        self.assertIn(ignored, results)

    def test_orders_outside_the_window_do_not_count(self):
        stale = self._product('Old Favourite', category=self.shoes)
        fresh = self._product('New Thing', category=self.shoes)
        customer = self._customer()
        order = self._purchase(customer, stale)
        Order.objects.filter(pk=order.pk).update(ordered_at=timezone.now() - timedelta(days=90))

        cache.clear()
        results = trending_products(limit=8)

        self.assertIn(fresh, results)
        self.assertIn(stale, results)

    def test_category_filter_restricts_results(self):
        shoe = self._product('Running Shoe', category=self.shoes)
        self._product('Frying Pan', category=self.kitchen)

        self.assertEqual(trending_products(limit=8, category='footwear'), [shoe])

    def test_results_are_cached(self):
        self._product('Running Shoe', category=self.shoes)

        first = trending_products(limit=8)
        self._product('Frying Pan', category=self.kitchen)
        second = trending_products(limit=8)

        # The second call is served from cache, so it cannot see the new row.
        self.assertEqual(len(first), len(second))

    def test_limit_is_respected(self):
        for i in range(6):
            self._product(f'Shoe {i}', category=self.shoes)

        self.assertEqual(len(trending_products(limit=3)), 3)


class PersonalizedProductsTests(RecommendationTestBase):
    def test_falls_back_to_trending_without_history(self):
        product = self._product('Running Shoe', category=self.shoes)
        customer = self._customer()

        self.assertEqual(personalized_products(customer, limit=8), [product])

    def test_anonymous_user_gets_trending(self):
        product = self._product('Running Shoe', category=self.shoes)

        self.assertEqual(personalized_products(None, limit=8), [product])

    def test_favourite_category_is_preferred(self):
        favourite = self._product('Running Shoe', category=self.shoes)
        same_category = self._product('Trail Shoe', category=self.shoes)
        other = self._product('Frying Pan', category=self.kitchen)
        customer = self._customer()
        Favourite.objects.create(customer=customer, product=favourite)

        results = personalized_products(customer, limit=8)

        # Favourites are not excluded the way purchases are -- wanting something
        # is a reason to show it again, owning it is not.
        self.assertIn(same_category, results)
        self.assertNotIn(other, results)

    def test_purchased_products_are_excluded(self):
        purchased = self._product('Running Shoe', category=self.shoes)
        suggestion = self._product('Trail Shoe', category=self.shoes)
        customer = self._customer()
        self._purchase(customer, purchased)

        results = personalized_products(customer, limit=8)

        self.assertNotIn(purchased, results)
        self.assertIn(suggestion, results)

    def test_interaction_events_build_a_profile(self):
        viewed = self._product('Running Shoe', category=self.shoes)
        same_category = self._product('Trail Shoe', category=self.shoes)
        self._product('Frying Pan', category=self.kitchen)
        customer = self._customer()
        InteractionEvent.objects.create(product=viewed, user=customer, event_type='view')

        results = personalized_products(customer, limit=8)

        self.assertIn(same_category, results)
        self.assertIn(viewed, results)


class ClampLimitTests(TestCase):
    def test_defaults_when_missing(self):
        self.assertEqual(clamp_limit(None), 8)
        self.assertEqual(clamp_limit(''), 8)

    def test_caps_at_maximum(self):
        self.assertEqual(clamp_limit(500), MAX_LIMIT)

    def test_rejects_non_numeric_and_non_positive(self):
        self.assertIsNone(clamp_limit('abc'))
        self.assertIsNone(clamp_limit(0))
        self.assertIsNone(clamp_limit(-3))


class RecommendationEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()
        self.category = Category.objects.create(name='Footwear')
        self.seed = Product.objects.create(
            store=self.vendor, name='Running Shoe', price='100.00', stock=5,
            category=self.category, approval_status='approved', publish_status='submitted',
        )
        self.sibling = Product.objects.create(
            store=self.vendor, name='Trail Shoe', price='105.00', stock=5,
            category=self.category, approval_status='approved', publish_status='submitted',
        )

    def test_related_returns_serialized_products(self):
        resp = self.client.get('/store/recommendations/', {'type': 'related', 'product': self.seed.slug})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in resp.data['data']]
        self.assertEqual(names, ['Trail Shoe'])

    def test_trending_requires_no_authentication(self):
        resp = self.client.get('/store/recommendations/', {'type': 'trending'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['data']), 2)

    def test_for_you_falls_back_to_trending_for_anonymous(self):
        resp = self.client.get('/store/recommendations/', {'type': 'for-you'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['data']), 2)

    def test_invalid_type_returns_400(self):
        resp = self.client.get('/store/recommendations/', {'type': 'magic'})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp.data['success'])

    def test_missing_type_returns_400(self):
        self.assertEqual(
            self.client.get('/store/recommendations/').status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_related_without_product_returns_400(self):
        resp = self.client.get('/store/recommendations/', {'type': 'related'})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_product_returns_400(self):
        resp = self.client.get('/store/recommendations/', {'type': 'related', 'product': 'nope'})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_limit_is_capped(self):
        for i in range(30):
            Product.objects.create(
                store=self.vendor, name=f'Shoe {i}', price='10.00', stock=5,
                category=self.category, approval_status='approved', publish_status='submitted',
            )

        resp = self.client.get('/store/recommendations/', {'type': 'trending', 'limit': 100})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(resp.data['data']), MAX_LIMIT)

    def test_invalid_limit_returns_400(self):
        resp = self.client.get('/store/recommendations/', {'type': 'trending', 'limit': 'lots'})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trending_by_category(self):
        other = Category.objects.create(name='Kitchen')
        Product.objects.create(
            store=self.vendor, name='Frying Pan', price='40.00', stock=5,
            category=other, approval_status='approved', publish_status='submitted',
        )

        resp = self.client.get('/store/recommendations/', {'type': 'trending', 'category': 'kitchen'})

        names = [item['name'] for item in resp.data['data']]
        self.assertEqual(names, ['Frying Pan'])


class InteractionEventEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()
        self.product = Product.objects.create(
            store=self.vendor, name='Running Shoe', price='100.00', stock=5,
            approval_status='approved', publish_status='submitted',
        )

    def test_anonymous_event_is_recorded(self):
        resp = self.client.post(
            '/store/events/',
            {'product': self.product.slug, 'event_type': 'view'},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        event = InteractionEvent.objects.get()
        self.assertIsNone(event.user)
        self.assertEqual(event.product, self.product)

    def test_authenticated_event_is_attributed_to_the_user(self):
        User = get_user_model()
        customer = User.objects.create_user(email='cust@example.com', password='pass123')
        self.client.force_authenticate(user=customer)

        resp = self.client.post(
            '/store/events/',
            {'product': self.product.slug, 'event_type': 'cart_add'},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        event = InteractionEvent.objects.get()
        self.assertEqual(event.user, customer)
        self.assertEqual(event.event_type, 'cart_add')

    def test_unknown_slug_returns_400_without_raising(self):
        resp = self.client.post(
            '/store/events/',
            {'product': 'does-not-exist', 'event_type': 'view'},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InteractionEvent.objects.exists())

    def test_invalid_event_type_returns_400(self):
        resp = self.client.post(
            '/store/events/',
            {'product': self.product.slug, 'event_type': 'teleport'},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InteractionEvent.objects.exists())

    def test_missing_fields_return_400(self):
        self.assertEqual(
            self.client.post('/store/events/', {}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST,
        )
