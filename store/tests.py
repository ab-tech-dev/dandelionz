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

