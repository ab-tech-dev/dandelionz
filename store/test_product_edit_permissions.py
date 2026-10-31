"""
Who may save an edit to a product (PATCH /store/products/<slug>/patch/).

Both the web and the mobile admin dashboards are built for BUSINESS_ADMIN accounts and show
them an edit screen. The endpoint only let in is_staff / is_superuser users, so a business
admin got "You do not have permission to update this product." on every product, including
ones they had created themselves.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from django.test import TestCase

from store.models import Product
from users.models import Vendor

User = get_user_model()


class ProductEditPermissionTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            'super@test.com', 'pw12345!', full_name='Super', is_verified=True)
        self.business_admin = User.objects.create_business_admin(
            'biz@test.com', 'pw12345!', full_name='Biz', is_verified=True)
        # An ADMIN-role account that is not a Django superuser or staff member.
        self.plain_admin = User.objects.create_user(
            'admin@test.com', 'pw12345!', full_name='Admin', role='ADMIN', is_verified=True)
        self.owner = User.objects.create_user(
            'owner@test.com', 'pw12345!', full_name='Owner', role='VENDOR', is_verified=True)
        self.rival = User.objects.create_user(
            'rival@test.com', 'pw12345!', full_name='Rival', role='VENDOR', is_verified=True)
        self.customer = User.objects.create_user(
            'buyer@test.com', 'pw12345!', full_name='Buyer', role='CUSTOMER', is_verified=True)

        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.owner, defaults={'store_name': 'Owner store'})
        Vendor.objects.get_or_create(user=self.rival, defaults={'store_name': 'Rival store'})
        self.product = Product.objects.create(
            store=self.vendor, name='Shirt', slug='shirt', price=Decimal('1000'), stock=3,
            publish_status='submitted', approval_status='approved')

    def _patch(self, user, slug='shirt'):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client.patch(
            reverse('patch-product', kwargs={'slug': slug}),
            {'description': 'edited'}, format='json')

    def test_every_admin_role_can_edit_any_product(self):
        for label, user in (
            ('superuser', self.superuser),
            ('business admin', self.business_admin),
            ('admin role without staff flags', self.plain_admin),
        ):
            with self.subTest(label):
                response = self._patch(user)
                self.assertEqual(response.status_code, 200, response.data)
                self.product.refresh_from_db()
                self.assertEqual(self.product.description, 'edited')
                Product.objects.filter(pk=self.product.pk).update(description='')

    def test_business_admin_can_edit_a_product_they_created_themselves(self):
        # CreateProductView binds an admin's product to a lightweight store for that account.
        store, _ = Vendor.objects.get_or_create(
            user=self.business_admin, defaults={'store_name': 'Business store'})
        Product.objects.create(
            store=store, name='Hat', slug='hat', price=Decimal('500'), stock=1,
            publish_status='submitted', approval_status='approved')

        self.assertEqual(self._patch(self.business_admin, slug='hat').status_code, 200)

    def test_vendor_can_edit_their_own_product(self):
        self.assertEqual(self._patch(self.owner).status_code, 200)

    def test_vendor_cannot_edit_another_vendors_product(self):
        response = self._patch(self.rival)

        self.assertEqual(response.status_code, 403)
        self.assertIn('do not own', str(response.data))
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.description, 'edited')

    def test_customer_cannot_edit_a_product(self):
        response = self._patch(self.customer)

        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.description, 'edited')

    def test_anonymous_visitor_cannot_edit_a_product(self):
        self.assertIn(self._patch(None).status_code, (401, 403))
