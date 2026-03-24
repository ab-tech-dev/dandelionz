from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from users.models import Vendor
from .models import Product, CartItem


class AddToCartPatchTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        # Customer
        self.customer = User.objects.create_user(email='cust@example.com', password='pass123')
        # Vendor and product
        self.vendor_user = User.objects.create_user(email='vendor@example.com', password='pass123', role='VENDOR')
        self.vendor = Vendor.objects.create(user=self.vendor_user, store_name='Test Shop', is_verified_vendor=True)
        self.product = Product.objects.create(store=self.vendor, name='Test Product', price='10.00', stock=100)
        self.client.force_authenticate(user=self.customer)

    def test_patch_creates_item_when_not_exists(self):
        resp = self.client.patch('/store/cart/add/', {'slug': self.product.slug, 'quantity': 3}, format='json')
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(resp.data['data']['quantity'], 3)

    def test_patch_updates_existing_item_quantity(self):
        # Add first via POST
        self.client.post('/store/cart/add/', {'slug': self.product.slug, 'quantity': 2}, format='json')
        resp = self.client.patch('/store/cart/add/', {'slug': self.product.slug, 'quantity': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['data']['quantity'], 5)

    def test_patch_removes_item_when_quantity_zero(self):
        self.client.post('/store/cart/add/', {'slug': self.product.slug, 'quantity': 2}, format='json')
        resp = self.client.patch('/store/cart/add/', {'slug': self.product.slug, 'quantity': 0}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(CartItem.objects.filter(cart=self.customer.cart, product=self.product).exists())


class ProductDeletePermissionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.vendor_user = User.objects.create_user(email='vendor@example.com', password='pass123', role='VENDOR')
        self.vendor = Vendor.objects.create(user=self.vendor_user, store_name='Test Shop 1', is_verified_vendor=True)
        self.other_vendor_user = User.objects.create_user(email='other_vendor@example.com', password='pass123', role='VENDOR')
        self.other_vendor = Vendor.objects.create(user=self.other_vendor_user, store_name='Test Shop 2', is_verified_vendor=True)

        self.admin_user = User.objects.create_user(email='admin@example.com', password='pass123', role='ADMIN', is_staff=True, is_superuser=True)

        self.own_product = Product.objects.create(store=self.vendor, name='Vendor Product', price='20.00', stock=10)
        self.other_product = Product.objects.create(store=self.other_vendor, name='Other Vendor Product', price='30.00', stock=5)

    def test_vendor_can_delete_own_product(self):
        self.client.force_authenticate(user=self.vendor_user)
        resp = self.client.delete(f'/store/products/{self.own_product.slug}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Product.objects.filter(pk=self.own_product.pk).exists())

    def test_vendor_cannot_delete_other_vendor_product(self):
        self.client.force_authenticate(user=self.vendor_user)
        resp = self.client.delete(f'/store/products/{self.other_product.slug}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Product.objects.filter(pk=self.other_product.pk).exists())

    def test_admin_can_delete_any_product(self):
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.delete(f'/store/products/{self.other_product.slug}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Product.objects.filter(pk=self.other_product.pk).exists())

