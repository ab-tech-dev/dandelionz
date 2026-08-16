"""
Regression coverage for a bug where AllowAny store endpoints returned 401
whenever the request carried a bad token, instead of treating the request as
anonymous.

DRF resolves authentication before permissions. CustomJWTAuthentication (like
its parent JWTAuthentication) *raises* on a missing/expired/malformed token
rather than returning None, and BaseAPIView.handle_exception turns that into
a hard 401 -- even on a view declaring permission_classes = [AllowAny]. In
practice this meant: log in, let the access token sit long enough to expire
(or the app holds on to one from a previous session), and public browsing
(search, recommendations, product detail, categories, ...) broke with
"Unauthorized" until the stale token was cleared.

OptionalJWTAuthentication (authentication/core/authentication.py) fixes this
by catching that specific failure and falling back to an anonymous request,
while still authenticating normally when the token is valid.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from users.models import Vendor
from .models import Category, Product


def _make_vendor(email='vendor-public@example.com'):
    User = get_user_model()
    user = User.objects.create_user(email=email, password='pass123', role='VENDOR')
    vendor = Vendor.objects.filter(user=user).first()
    if vendor is None:
        vendor = Vendor.objects.create(user=user, store_name='Public Access Shop', is_verified_vendor=True)
    return vendor


class PublicEndpointsToleratesBadTokenTests(TestCase):
    """
    Covers the two AllowAny views seen 401ing in production logs. The same
    fix applies to every other AllowAny view in store/views.py, but these two
    are enough to prove the mechanism without duplicating this whole class
    eleven times.
    """

    def setUp(self):
        self.client = APIClient()
        self.vendor = _make_vendor()
        Category.objects.create(name='Kitchen Appliances')
        Product.objects.create(
            store=self.vendor, name='Maxi microwave oven', price='105600.00', stock=5,
            approval_status='approved', publish_status='submitted',
        )

    def test_product_list_ignores_a_malformed_bearer_token(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')

        resp = self.client.get('/store/products/', {'search': 'microwave'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_recommendations_ignores_a_malformed_bearer_token(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer not-a-real-token')

        resp = self.client.get('/store/recommendations/', {'type': 'trending'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_product_list_ignores_an_expired_access_token(self):
        """
        This is the actual production scenario: a real, correctly-signed
        token that's simply past its exp claim -- e.g. one the app held on
        to from a previous session.
        """
        token = AccessToken.for_user(self.vendor.user)
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        resp = self.client.get('/store/products/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_valid_token_still_authenticates_normally(self):
        """The fix must not turn every request anonymous -- a good token still works."""
        token = AccessToken.for_user(self.vendor.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        resp = self.client.get('/store/products/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)