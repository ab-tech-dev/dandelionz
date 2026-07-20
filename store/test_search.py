"""
Search ranking tests.

Most of these are a *contract*: they assert orderings that must hold on both
Postgres and SQLite, so the portable fallback the test suite runs on stays
honest about the production path. Tests that exercise Postgres-only behaviour
(trigram typo tolerance) are marked to skip elsewhere.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from unittest import skipUnless

from users.models import Vendor
from .models import Category, Product
from .search import search_products


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


class SearchRankingContractTests(TestCase):
    """Ordering rules that must hold identically on every backend."""

    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()
        self.category = Category.objects.create(name='Footwear')

    def _product(self, name, **kwargs):
        kwargs.setdefault('price', '10.00')
        kwargs.setdefault('stock', 5)
        kwargs.setdefault('approval_status', 'approved')
        kwargs.setdefault('publish_status', 'submitted')
        return Product.objects.create(store=self.vendor, name=name, **kwargs)

    def _search(self, query):
        return list(search_products(Product.objects.all(), query))

    def test_exact_name_match_outranks_description_mention(self):
        mentioned = self._product('Leather Boot', description='Great with any sneakers you own')
        exact = self._product('Sneakers')

        results = self._search('Sneakers')

        self.assertEqual(results[0], exact)
        self.assertIn(mentioned, results)

    def test_name_prefix_outranks_mid_name_match(self):
        prefix = self._product('Running Shoes')
        contains = self._product('Trail Running Shoes')

        results = self._search('Running')

        self.assertEqual(results[0], prefix)
        self.assertIn(contains, results)

    def test_tags_are_searchable(self):
        """Regression: tags existed on the model but search ignored them."""
        tagged = self._product('Mystery Item', tags='waterproof,hiking')

        self.assertIn(tagged, self._search('waterproof'))

    def test_brand_is_searchable(self):
        branded = self._product('Mystery Item', brand='Umbro')

        self.assertIn(branded, self._search('Umbro'))

    def test_category_name_is_searchable(self):
        categorised = self._product('Mystery Item', category=self.category)

        self.assertIn(categorised, self._search('Footwear'))

    def test_in_stock_breaks_tie_between_equal_matches(self):
        out_of_stock = self._product('Sneakers', stock=0)
        in_stock = self._product('Sneakers', stock=3)

        results = self._search('Sneakers')

        self.assertEqual(results[0], in_stock)
        self.assertEqual(results[1], out_of_stock)

    def test_availability_never_outranks_relevance(self):
        """An out-of-stock exact match still beats an in-stock description hit."""
        exact_no_stock = self._product('Sneakers', stock=0)
        described_in_stock = self._product('Boot', description='like sneakers', stock=50)

        self.assertEqual(self._search('Sneakers')[0], exact_no_stock)

    def test_non_matching_products_are_excluded(self):
        self._product('Sneakers')
        self._product('Toaster')

        results = self._search('Sneakers')

        self.assertEqual(len(results), 1)

    def test_empty_query_returns_queryset_untouched(self):
        self._product('Sneakers')
        self._product('Toaster')

        self.assertEqual(len(self._search('')), 2)
        self.assertEqual(len(self._search(None)), 2)
        self.assertEqual(len(self._search('   ')), 2)


def _items(response):
    """
    Unwrap the product list payload.

    The view only nests under 'results' when a page is returned, so handle both
    shapes rather than assuming one.
    """
    payload = response.data
    if 'results' in payload:
        payload = payload['results']
    return payload['data']


class SearchEndpointTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()
        self.category = Category.objects.create(name='Footwear')
        Product.objects.create(
            store=self.vendor, name='Sneakers', price='10.00', stock=5,
            category=self.category, approval_status='approved', publish_status='submitted',
        )
        Product.objects.create(
            store=self.vendor, name='Toaster', price='90.00', stock=5,
            approval_status='approved', publish_status='submitted',
        )

    def test_search_filters_product_list(self):
        resp = self.client.get('/store/products/', {'search': 'Sneakers'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in _items(resp)]
        self.assertEqual(names, ['Sneakers'])

    def test_explicit_ordering_overrides_relevance(self):
        """Searching must not silently discard the documented ?ordering= param."""
        Product.objects.create(
            store=self.vendor, name='Sneakers Deluxe', price='5.00', stock=5,
            approval_status='approved', publish_status='submitted',
        )

        resp = self.client.get('/store/products/', {'search': 'Sneakers', 'ordering': 'price'})

        prices = [float(item['price']) for item in _items(resp)]
        self.assertEqual(prices, sorted(prices))

    def test_unapproved_products_stay_hidden_from_search(self):
        Product.objects.create(
            store=self.vendor, name='Sneakers Secret', price='10.00', stock=5,
            approval_status='pending', publish_status='submitted',
        )

        resp = self.client.get('/store/products/', {'search': 'Sneakers'})

        names = [item['name'] for item in _items(resp)]
        self.assertNotIn('Sneakers Secret', names)


class SearchSuggestionsTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()
        self.category = Category.objects.create(name='Footwear')
        Product.objects.create(
            store=self.vendor, name='Sneakers', price='10.00', stock=5,
            category=self.category, approval_status='approved', publish_status='submitted',
        )

    def test_short_query_returns_empty_without_querying(self):
        resp = self.client.get('/store/products/suggestions/', {'q': 'S'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['data'], {'products': [], 'categories': []})

    def test_returns_product_and_category_suggestions(self):
        resp = self.client.get('/store/products/suggestions/', {'q': 'Foot'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [c['name'] for c in resp.data['data']['categories']],
            ['Footwear'],
        )

    def test_suggestions_are_capped(self):
        for i in range(15):
            Product.objects.create(
                store=self.vendor, name=f'Sneakers {i}', price='10.00', stock=5,
                approval_status='approved', publish_status='submitted',
            )

        resp = self.client.get('/store/products/suggestions/', {'q': 'Sneakers'})

        self.assertLessEqual(len(resp.data['data']['products']), 8)

    def test_suggestions_require_no_authentication(self):
        resp = self.client.get('/store/products/suggestions/', {'q': 'Sneakers'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)


@skipUnless(connection.vendor == 'postgresql', 'Full-text search requires PostgreSQL')
class PostgresFullTextSearchTests(TestCase):
    """
    Postgres-only behaviour. These skip on the local SQLite suite and run in CI,
    which is the only place the production search path gets exercised.
    """

    def setUp(self):
        cache.clear()
        self.vendor = _make_vendor()

    def _product(self, name, **kwargs):
        kwargs.setdefault('price', '10.00')
        kwargs.setdefault('stock', 5)
        kwargs.setdefault('approval_status', 'approved')
        kwargs.setdefault('publish_status', 'submitted')
        return Product.objects.create(store=self.vendor, name=name, **kwargs)

    def test_stemming_matches_word_variants(self):
        """Full-text search should match 'running' against 'run'."""
        product = self._product('Trail Runner', description='Built for running fast')

        self.assertIn(product, list(search_products(Product.objects.all(), 'run')))

    def test_typo_tolerance_when_trigram_available(self):
        from .search import _has_trigram

        if not _has_trigram():
            self.skipTest("pg_trgm not installed; run 'CREATE EXTENSION pg_trgm;' to enable")

        product = self._product('Sneakers')

        self.assertIn(product, list(search_products(Product.objects.all(), 'snekers')))
