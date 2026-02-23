from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from store.models import Cart, CartItem, Product
from transactions.models import Order
from users.models import Customer, Vendor


class CheckoutShippingFeeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.customer_user = User.objects.create_user(
            email="customer@test.com",
            password="pass12345",
            role="CUSTOMER",
        )
        self.vendor_user = User.objects.create_user(
            email="vendor@test.com",
            password="pass12345",
            role="VENDOR",
        )

        self.customer_profile, _ = Customer.objects.get_or_create(user=self.customer_user)
        self.customer_profile.shipping_address = "123 Main Street"
        self.customer_profile.city = "Lagos"
        self.customer_profile.country = "Nigeria"
        self.customer_profile.postal_code = "100001"
        self.customer_profile.shipping_latitude = None
        self.customer_profile.shipping_longitude = None
        self.customer_profile.save()

        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.vendor_user,
            defaults={
                "store_name": "Demo Store",
                "address": "45 Market Road",
                "store_latitude": None,
                "store_longitude": None,
            },
        )
        self.vendor.store_name = "Demo Store"
        self.vendor.address = "45 Market Road"
        self.vendor.store_latitude = None
        self.vendor.store_longitude = None
        self.vendor.save()

        self.cart = Cart.objects.create(customer=self.customer_user)
        self.client.force_authenticate(user=self.customer_user)

    @patch("transactions.views._notify_checkout")
    @patch("transactions.views.Paystack.initialize_payment")
    @patch("transactions.delivery_service.DeliveryFeeCalculator.calculate_fee")
    @patch("transactions.views.geocode_address")
    def test_checkout_applies_shipping_fee_when_subtotal_gt_15000_with_vendor_address_fallback(
        self,
        mock_geocode,
        mock_calculate_fee,
        mock_initialize_payment,
        mock_notify_checkout,
    ):
        # Keep customer coordinates present so this test isolates vendor address fallback.
        self.customer_profile.shipping_latitude = 6.5000
        self.customer_profile.shipping_longitude = 3.3000
        self.customer_profile.save(update_fields=["shipping_latitude", "shipping_longitude"])

        product = Product.objects.create(
            store=self.vendor,
            name="Phone",
            price=Decimal("16000.00"),
            stock=10,
        )
        CartItem.objects.create(cart=self.cart, product=product, quantity=1)

        # Vendor geocode fallback.
        mock_geocode.return_value = (6.6000, 3.3000)
        mock_calculate_fee.return_value = {
            "success": True,
            "fee": 5000.0,
            "distance": "10.00 km",
            "duration": "20 mins",
            "distance_miles": 6.21,
            "error": None,
            "cached": False,
        }
        mock_initialize_payment.return_value = {
            "data": {"authorization_url": "https://paystack.test/auth"}
        }

        response = self.client.post("/transactions/checkout/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["delivery_fee"], 5000.0)

        order = Order.objects.get(order_id=response.data["data"]["order_id"])
        self.assertEqual(order.delivery_fee, Decimal("5000.00"))
        self.assertEqual(order.total_price, Decimal("21000.00"))

        self.customer_profile.refresh_from_db()
        self.vendor.refresh_from_db()
        self.assertEqual(self.customer_profile.shipping_latitude, 6.5)
        self.assertEqual(self.customer_profile.shipping_longitude, 3.3)
        self.assertEqual(self.vendor.store_latitude, 6.6)
        self.assertEqual(self.vendor.store_longitude, 3.3)
        self.assertEqual(mock_geocode.call_count, 1)
        mock_calculate_fee.assert_called_once()
        mock_notify_checkout.assert_called_once()

    @patch("transactions.views._notify_checkout")
    @patch("transactions.views.Paystack.initialize_payment")
    @patch("transactions.views.geocode_address")
    def test_checkout_does_not_apply_shipping_fee_when_subtotal_equals_15000(
        self,
        mock_geocode,
        mock_initialize_payment,
        mock_notify_checkout,
    ):
        product = Product.objects.create(
            store=self.vendor,
            name="Headset",
            price=Decimal("15000.00"),
            stock=10,
        )
        CartItem.objects.create(cart=self.cart, product=product, quantity=1)
        mock_initialize_payment.return_value = {
            "data": {"authorization_url": "https://paystack.test/auth"}
        }

        response = self.client.post("/transactions/checkout/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["delivery_fee"], 0)

        order = Order.objects.get(order_id=response.data["data"]["order_id"])
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.total_price, Decimal("15000.00"))
        self.assertEqual(mock_geocode.call_count, 0)
        mock_notify_checkout.assert_called_once()


class OrderDeliveryFeeEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.customer_user = User.objects.create_user(
            email="customer_fee@test.com",
            password="pass12345",
            role="CUSTOMER",
        )
        self.other_customer_user = User.objects.create_user(
            email="other_customer_fee@test.com",
            password="pass12345",
            role="CUSTOMER",
        )

        self.order = Order.objects.create(
            customer=self.customer_user,
            delivery_fee=Decimal("3200.00"),
            delivery_distance="12.00 km",
            delivery_duration="25 mins",
            delivery_distance_miles=7.46,
        )

    def test_customer_can_fetch_own_order_delivery_fee(self):
        self.client.force_authenticate(user=self.customer_user)

        response = self.client.get(f"/transactions/orders/{self.order.order_id}/delivery-fee/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["order_id"], str(self.order.order_id))
        self.assertEqual(response.data["data"]["delivery_fee"], 3200.0)
        self.assertEqual(response.data["data"]["delivery_distance"], "12.00 km")
        self.assertEqual(response.data["data"]["delivery_duration"], "25 mins")
        self.assertEqual(response.data["data"]["delivery_distance_miles"], 7.46)
        self.assertTrue(response.data["data"]["delivery_applied"])

    def test_customer_cannot_fetch_another_customers_order_delivery_fee(self):
        self.client.force_authenticate(user=self.other_customer_user)

        response = self.client.get(f"/transactions/orders/{self.order.order_id}/delivery-fee/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
