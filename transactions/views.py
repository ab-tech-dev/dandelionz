import hmac
import hashlib
import uuid
import logging
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db import transaction

from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.core.permissions import IsVendor, IsCustomer, IsAdmin
from transactions.models import Wallet, WalletTransaction, InstallmentPlan, InstallmentPayment
from users.models import Notification

logger = logging.getLogger(__name__)

from .models import Order, OrderItem, Payment, TransactionLog, Refund
from store.models import Cart, CartItem
from .serializers import (
    OrderSerializer,
    OrderReceiptSerializer,
    OrderItemSerializer,
    TransactionLogSerializer,
    PaymentSerializer,
    RefundSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
    InstallmentPlanSerializer,
    InstallmentPaymentSerializer,
    InstallmentCheckoutSerializer,
    RefundActionSerializer,
    InitializeInstallmentPaymentSerializer,
    VerifyPaymentSerializer,
    CommissionAnalyticsQuerySerializer,
    CommissionAnalyticsResponseSerializer
)
from .paystack import Paystack
from authentication.core.response import standardized_response

PLATFORM_COMMISSION = Decimal("0.10")
EXPECTED_CURRENCY = "NGN"

# ----------------------
# Custom Throttle Classes
# ----------------------
class PaymentVerificationThrottle(UserRateThrottle):
    """
    Stricter rate limit for payment verification endpoints.
    Limits: 5 requests per minute per user
    Prevents abuse of payment verification endpoints
    """
    scope = 'payment_verification'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Override default throttle_rates if needed
        # This can be set in settings.py with:
        # REST_FRAMEWORK = {
        #     'DEFAULT_THROTTLE_RATES': {
        #         'payment_verification': '5/min',
        #         'installment_verification': '5/min',
        #     }
        # }


class InstallmentVerificationThrottle(UserRateThrottle):
    """
    Stricter rate limit for installment payment verification endpoints.
    Limits: 5 requests per minute per user
    Prevents abuse of installment payment verification
    """
    scope = 'installment_verification'


class CheckoutThrottle(UserRateThrottle):
    """
    Rate limit for checkout endpoints to prevent abuse.
    Limits: 10 requests per minute per user
    Prevents rapid-fire checkout attempts
    """
    scope = 'checkout'

# ----------------------
# Helper functions
# ----------------------
def credit_vendors_for_order(order, source_prefix="Order"):
    """
    Credit all vendors for an order based on their items' subtotals.
    Deducts platform commission (10%) from vendor share.
    
    Args:
        order: Order instance
        source_prefix: Prefix for the wallet transaction source (default: "Order")
    """
    import logging
    logger = logging.getLogger(__name__)
    
    for item in order.order_items.all():
        vendor = item.product.store
        if not vendor:
            continue
        vendor_share = item.item_subtotal * (Decimal("1.00") - PLATFORM_COMMISSION)
        commission_amount = item.item_subtotal * PLATFORM_COMMISSION
        
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=vendor)
        wallet.credit(vendor_share, source=f"{source_prefix} {order.order_id}")
        
        # Log the transaction for audit trail
        TransactionLog.objects.create(
            order=order,
            action=TransactionLog.Action.VENDOR_CREDITED,
            level=TransactionLog.Level.SUCCESS,
            message=f"Vendor {vendor.email} credited ₦{vendor_share} for delivery (Item: {item.product.name})",
            related_user=vendor,
            amount=vendor_share,
            metadata={
                "vendor_id": vendor.id,
                "vendor_email": vendor.email,
                "item_id": item.id,
                "item_name": item.product.name,
                "item_subtotal": str(item.item_subtotal),
                "commission_rate": "10%",
                "commission_amount": str(commission_amount),
            }
        )
        
        logger.info(
            f"Vendor credited: {vendor.email} | Amount: ₦{vendor_share} | "
            f"Commission: ₦{commission_amount} | Order: {order.order_id}"
        )

# ----------------------
# Custom permissions
# ----------------------
class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "customer", None)
        return bool(request.user and (request.user.is_staff or owner == request.user))

# ----------------------
# Order endpoints
# ----------------------
class OrderListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="list_orders",
        operation_summary="List Orders",
        operation_description="Retrieve list of orders. Customers see their own orders; admins see all orders.",
        tags=["Orders"],
        responses={
            200: OrderSerializer(many=True),
            401: openapi.Response("Unauthorized"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="create_order",
        operation_summary="Create Order",
        operation_description="Create a new order from cart items.",
        tags=["Orders"],
        request_body=OrderSerializer,
        responses={
            201: OrderSerializer,
            400: openapi.Response("Bad Request"),
            401: openapi.Response("Unauthorized"),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all().order_by("-ordered_at")
        return Order.objects.filter(customer=user).order_by("-ordered_at")

    def perform_create(self, serializer):
        order = serializer.save(customer=self.request.user)
        order.update_total()
        vendors = {item.vendor for item in order.order_items.all() if item.vendor}
        for vendor in vendors:
            Notification.objects.create(
                recipient=vendor,
                title="New Order Received",
                message=f"You received a new order {order.order_id}."
            )

class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    lookup_field = "order_id"

    @swagger_auto_schema(
        operation_id="retrieve_order",
        operation_summary="Get Order Details",
        operation_description="""Retrieve complete order details including tracking timeline.

Returns:
- order_id: Unique order identifier
- status: Current order status (PENDING, PAID, SHIPPED, DELIVERED, RETURNED, CANCELED)
- timeline: Array of status progression events with timestamps and completion status
- order_items: Items in the order
- payment: Payment information
- shipping_address: Delivery address
- tracking_number: For shipment tracking
- Financial summary: subtotal, delivery_fee, discount, total_price""",
        tags=["Orders"],
        responses={
            200: OrderSerializer,
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="update_order",
        operation_summary="Update Order",
        operation_description="Update order details (partial update).",
        tags=["Orders"],
        request_body=OrderSerializer,
        responses={
            200: OrderSerializer,
            400: openapi.Response("Bad Request"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="delete_order",
        operation_summary="Delete Order",
        operation_description="Delete a specific order.",
        tags=["Orders"],
        responses={
            204: openapi.Response("No Content"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(customer=self.request.user)

# ----------------------
# OrderItem endpoints
# ----------------------
class OrderItemListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    @swagger_auto_schema(
        operation_id="list_order_items",
        operation_summary="List Order Items",
        operation_description="Retrieve items in a specific order.",
        tags=["Order Items"],
        responses={
            200: OrderItemSerializer(many=True),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="create_order_item",
        operation_summary="Create Order Item",
        operation_description="Add an item to an order.",
        tags=["Order Items"],
        request_body=OrderItemSerializer,
        responses={
            201: OrderItemSerializer,
            400: openapi.Response("Bad Request"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_queryset(self):
        order_id = self.kwargs.get("order_id")
        user = self.request.user
        if user.is_staff:
            return OrderItem.objects.filter(order__order_id=order_id)
        return OrderItem.objects.filter(order__order_id=order_id, order__customer=user)

    def perform_create(self, serializer):
        order = get_object_or_404(Order, order_id=self.kwargs.get("order_id"))
        order_item = serializer.save(order=order)
        order.update_total()
        vendor = order_item.vendor
        if vendor:
            Notification.objects.create(
                recipient=vendor,
                title="New Order Item Received",
                message=f"You have a new order item: {order_item.product.name} x {order_item.quantity} "
                        f"in order {order.order_id} from {order.customer.email}."
            )

class OrderItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="retrieve_order_item",
        operation_summary="Get Order Item Details",
        operation_description="Retrieve details of a specific order item.",
        tags=["Order Items"],
        responses={
            200: OrderItemSerializer,
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="update_order_item",
        operation_summary="Update Order Item",
        operation_description="Update details of an order item.",
        tags=["Order Items"],
        request_body=OrderItemSerializer,
        responses={
            200: OrderItemSerializer,
            400: openapi.Response("Bad Request"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="delete_order_item",
        operation_summary="Delete Order Item",
        operation_description="Remove an item from an order.",
        tags=["Order Items"],
        responses={
            204: openapi.Response("No Content"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return OrderItem.objects.none()
        if user.is_staff:
            return OrderItem.objects.all()
        return OrderItem.objects.filter(order__customer=user)

# ----------------------
# Transaction logs (admin only)
# ----------------------
class TransactionLogListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = TransactionLogSerializer
    queryset = TransactionLog.objects.all().order_by('-created_at')

    @swagger_auto_schema(
        operation_id="list_transaction_logs",
        operation_summary="List Transaction Logs",
        operation_description="Retrieve all transaction logs (admin only).",
        tags=["Transactions"],
        responses={
            200: TransactionLogSerializer(many=True),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

# ----------------------
# Checkout Endpoint (New)
# ----------------------
class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [CheckoutThrottle]

    @swagger_auto_schema(
        operation_id="checkout_single_payment",
        operation_summary="Checkout with Single Payment",
        operation_description="Process checkout and initialize Paystack payment for cart items.",
        tags=["Checkout"],
        responses={
            201: openapi.Response("Payment initialized", schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'authorization_url': openapi.Schema(type=openapi.TYPE_STRING),
                    'reference': openapi.Schema(type=openapi.TYPE_STRING),
                    'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                }
            )),
            400: openapi.Response("Cart is empty or invalid"),
            401: openapi.Response("Unauthorized"),
        },
    )
    def post(self, request):
        user = request.user
        logger.info(f"Checkout initiated for user: {user.uuid}")
        
        cart = Cart.objects.filter(customer=user).first()
        if not cart:
            logger.warning(f"Checkout failed: No cart found for user {user.uuid}")
            return Response(
                standardized_response(success=False, error="Cart is empty"),
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_items = CartItem.objects.select_related("product").filter(cart=cart)
        if not cart_items.exists():
            logger.warning(f"Checkout failed: Cart {cart.id} has no items for user {user.uuid}")
            return Response(
                standardized_response(success=False, error="Cart has no items"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check customer has shipping address with coordinates
        if not hasattr(user, 'customer_profile'):
            logger.warning(f"Checkout failed: User {user.uuid} has no customer profile")
            return Response(
                standardized_response(success=False, error="Customer profile not found. Please create one before checking out."),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        customer_profile = user.customer_profile
        if not customer_profile.shipping_latitude or not customer_profile.shipping_longitude:
            if settings.ENFORCE_DELIVERY_FEE_ON_CHECKOUT:
                logger.warning(f"Checkout failed: User {user.uuid} has no shipping address coordinates")
                return Response(
                    standardized_response(success=False, error="Shipping address with coordinates is required. Please update your profile with your shipping location before checking out."),
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                logger.info(f"Delivery fee enforcement disabled: Allowing checkout without coordinates for user {user.uuid}")

        try:
            with transaction.atomic():
                # 1. Create Order
                order = Order.objects.create(customer=user)
                logger.info(f"Order created: {order.order_id} for user {user.uuid}")

                # 2. Convert CartItems → OrderItems (using discounted price)
                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        price_at_purchase=item.product.get_final_price
                    )

                # 3. Auto-retrieve and set vendor & customer delivery coordinates
                try:
                    # Get vendor (store) coordinates from the first product vendor
                    first_item = cart_items.first()
                    if first_item and first_item.product and hasattr(first_item.product, 'store'):
                        vendor = first_item.product.store
                        if vendor and hasattr(vendor, 'store_latitude') and hasattr(vendor, 'store_longitude'):
                            if vendor.store_latitude and vendor.store_longitude:
                                order.restaurant_lat = vendor.store_latitude
                                order.restaurant_lng = vendor.store_longitude
                                logger.info(f"Vendor coordinates retrieved for order {order.order_id}: ({vendor.store_latitude}, {vendor.store_longitude})")
                    
                    # Get customer coordinates from customer profile
                    if hasattr(user, 'customer_profile'):
                        customer_profile = user.customer_profile
                        if hasattr(customer_profile, 'shipping_latitude') and hasattr(customer_profile, 'shipping_longitude'):
                            if customer_profile.shipping_latitude and customer_profile.shipping_longitude:
                                order.customer_lat = customer_profile.shipping_latitude
                                order.customer_lng = customer_profile.shipping_longitude
                                logger.info(f"Customer coordinates retrieved for order {order.order_id}: ({customer_profile.shipping_latitude}, {customer_profile.shipping_longitude})")
                    
                    # Calculate delivery fee if both vendor and customer coordinates are available
                    if order.restaurant_lat and order.restaurant_lng and order.customer_lat and order.customer_lng:
                        try:
                            order.calculate_and_save_delivery_fee()
                            logger.info(f"Delivery fee calculated: ${order.delivery_fee} for order {order.order_id}")
                        except Exception as e:
                            logger.warning(f"Delivery fee calculation failed for order {order.order_id}: {str(e)}")
                            # Continue checkout even if delivery fee fails - can be calculated later
                            pass
                    else:
                        logger.warning(f"Incomplete coordinates for order {order.order_id}. Vendor: ({order.restaurant_lat}, {order.restaurant_lng}), Customer: ({order.customer_lat}, {order.customer_lng})")
                except Exception as e:
                    logger.warning(f"Error retrieving delivery coordinates for order {order.order_id}: {str(e)}")
                    # Continue checkout even if coordinate retrieval fails
                    pass

                # 4. Calculate total
                order.update_total()
                logger.info(f"Order total calculated: {order.total_price} for order {order.order_id}")

                # 5. Create or reset Payment
                reference = f"{order.order_id}-{uuid.uuid4().hex[:10]}"
                payment, _ = Payment.objects.get_or_create(
                    order=order,
                    defaults={
                        "amount": order.total_price,
                        "reference": reference,
                    }
                )
                payment.amount = order.total_price
                payment.reference = reference
                payment.verified = False
                payment.status = 'PENDING'
                payment.save()

                # 6. Initialize Paystack
                paystack = Paystack()
                response = paystack.initialize_payment(
                    email=user.email,
                    amount=payment.amount,
                    reference=payment.reference,
                    callback_url=settings.PAYSTACK_CALLBACK_URL
                )
                logger.info(f"Paystack payment initialized for order {order.order_id}")

                # Clear cart (vendors will be notified when payment is verified)
                cart_items.delete()
                logger.info(f"Cart cleared for user {user.uuid}")

            return Response(
                standardized_response(
                    data={
                        "order_id": str(order.order_id),
                        "authorization_url": response["data"]["authorization_url"],
                        "reference": payment.reference,
                        "amount": float(payment.amount),
                        "delivery_fee": float(order.delivery_fee) if order.delivery_fee else 0
                    },
                    message="Checkout initialized successfully"
                ),
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.error(f"Checkout error for user {user.uuid}: {str(e)}", exc_info=True)
            return Response(
                standardized_response(success=False, error=f"Checkout failed: {str(e)}"),
                status=status.HTTP_400_BAD_REQUEST
            )


# ----------------------
# Installment Checkout Endpoint
# ----------------------
class InstallmentCheckoutView(APIView):
    """
    Checkout with installment payment plan.
    Creates order and installment plan, then initializes payment for first installment.
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="checkout_installment",
        operation_summary="Checkout with Installment Plan",
        operation_description="""Create an order with installment payment plan and initialize first payment via Paystack.
        
Duration options: 1_month, 3_months, 6_months, 1_year""",
        tags=["Installments"],
        request_body=InstallmentCheckoutSerializer,
        responses={
            201: openapi.Response("Installment plan created", schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'order_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'installment_plan_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'duration': openapi.Schema(type=openapi.TYPE_STRING),
                    'total_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'number_of_installments': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'installment_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'first_installment_reference': openapi.Schema(type=openapi.TYPE_STRING),
                    'authorization_url': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )),
            400: openapi.Response("Cart is empty or invalid duration"),
            401: openapi.Response("Unauthorized"),
        },
    )
    def post(self, request):
        user = request.user
        logger.info(f"Installment checkout initiated for user: {user.uuid}")
        
        cart = Cart.objects.filter(customer=user).first()
        
        if not cart:
            logger.warning(f"Installment checkout failed: No cart found for user {user.uuid}")
            return Response(
                standardized_response(success=False, error="Cart is empty"),
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_items = CartItem.objects.select_related("product").filter(cart=cart)
        if not cart_items.exists():
            logger.warning(f"Installment checkout failed: Cart {cart.id} has no items for user {user.uuid}")
            return Response(
                standardized_response(success=False, error="Cart has no items"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check customer has shipping address with coordinates
        if not hasattr(user, 'customer_profile'):
            logger.warning(f"Installment checkout failed: User {user.uuid} has no customer profile")
            return Response(
                standardized_response(success=False, error="Customer profile not found. Please create one before checking out."),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        customer_profile = user.customer_profile
        if not customer_profile.shipping_latitude or not customer_profile.shipping_longitude:
            if settings.ENFORCE_DELIVERY_FEE_ON_CHECKOUT:
                logger.warning(f"Installment checkout failed: User {user.uuid} has no shipping address coordinates")
                return Response(
                    standardized_response(success=False, error="Shipping address with coordinates is required. Please update your profile with your shipping location before checking out."),
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                logger.info(f"Delivery fee enforcement disabled: Allowing installment checkout without coordinates for user {user.uuid}")

        # Validate installment duration
        serializer = InstallmentCheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Installment checkout validation failed for user {user.uuid}: {serializer.errors}")
            return Response(
                standardized_response(success=False, error=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )

        duration = serializer.validated_data['duration']

        try:
            with transaction.atomic():
                # 1. Create Order
                order = Order.objects.create(customer=user)
                logger.info(f"Order created: {order.order_id} for user {user.uuid}")

                # 2. Convert CartItems → OrderItems (using discounted price)
                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        price_at_purchase=item.product.get_final_price,
                    )

                # 3. Auto-retrieve and set vendor & customer delivery coordinates
                try:
                    # Get vendor (store) coordinates from the first product vendor
                    first_item = cart_items.first()
                    if first_item and first_item.product and hasattr(first_item.product, 'store'):
                        vendor = first_item.product.store
                        if vendor and hasattr(vendor, 'store_latitude') and hasattr(vendor, 'store_longitude'):
                            if vendor.store_latitude and vendor.store_longitude:
                                order.restaurant_lat = vendor.store_latitude
                                order.restaurant_lng = vendor.store_longitude
                                logger.info(f"Vendor coordinates retrieved for order {order.order_id}: ({vendor.store_latitude}, {vendor.store_longitude})")
                    
                    # Get customer coordinates from customer profile
                    if hasattr(user, 'customer_profile'):
                        customer_profile = user.customer_profile
                        if hasattr(customer_profile, 'shipping_latitude') and hasattr(customer_profile, 'shipping_longitude'):
                            if customer_profile.shipping_latitude and customer_profile.shipping_longitude:
                                order.customer_lat = customer_profile.shipping_latitude
                                order.customer_lng = customer_profile.shipping_longitude
                                logger.info(f"Customer coordinates retrieved for order {order.order_id}: ({customer_profile.shipping_latitude}, {customer_profile.shipping_longitude})")
                    
                    # Calculate delivery fee if both vendor and customer coordinates are available
                    if order.restaurant_lat and order.restaurant_lng and order.customer_lat and order.customer_lng:
                        try:
                            order.calculate_and_save_delivery_fee()
                            logger.info(f"Delivery fee calculated: ${order.delivery_fee} for order {order.order_id}")
                        except Exception as e:
                            logger.warning(f"Delivery fee calculation failed for order {order.order_id}: {str(e)}")
                            # Continue checkout even if delivery fee fails - can be calculated later
                            pass
                    else:
                        logger.warning(f"Incomplete coordinates for order {order.order_id}. Vendor: ({order.restaurant_lat}, {order.restaurant_lng}), Customer: ({order.customer_lat}, {order.customer_lng})")
                except Exception as e:
                    logger.warning(f"Error retrieving delivery coordinates for order {order.order_id}: {str(e)}")
                    # Continue checkout even if coordinate retrieval fails
                    pass

                # 4. Calculate total
                order.update_total()
                logger.info(f"Order total calculated: {order.total_price} for order {order.order_id}")

                # 5. Create Installment Plan
                num_installments = InstallmentPlan.DURATION_INSTALLMENTS.get(duration, 1)
                # Calculate base amount, rounded down to avoid overcharge
                base_amount = (order.total_price / Decimal(num_installments)).quantize(
                    Decimal("0.01"), rounding='ROUND_DOWN'
                )
                remainder = order.total_price - (base_amount * num_installments)
                
                installment_plan = InstallmentPlan.objects.create(
                    order=order,
                    duration=duration,
                    total_amount=order.total_price,
                    installment_amount=base_amount,
                    number_of_installments=num_installments,
                    status='ACTIVE',
                    vendors_credited=False
                )
                logger.info(f"Installment plan created: {installment_plan.id} for order {order.order_id}")

                # 6. Create individual installment payment records
                current_date = timezone.now()
                interval = timedelta(days=30)  # 30 days between each installment

                for i in range(1, num_installments + 1):
                    due_date = current_date + (interval * i)
                    # Add remainder to last installment to ensure total equals order total
                    amount = base_amount + remainder if i == num_installments else base_amount
                    InstallmentPayment.objects.create(
                        installment_plan=installment_plan,
                        payment_number=i,
                        amount=amount,
                        due_date=due_date,
                        reference=f"{order.order_id}-installment-{i}"
                    )

                # 7. Initialize payment for first installment
                first_installment = installment_plan.installments.first()
                paystack = Paystack()
                response = paystack.initialize_payment(
                    email=user.email,
                    amount=first_installment.amount,
                    reference=first_installment.reference,
                    callback_url=settings.PAYSTACK_CALLBACK_URL
                )
                logger.info(f"Paystack payment initialized for installment plan {installment_plan.id}")

                # Clear cart (vendors will be notified when payment is verified)
                cart_items.delete()
                logger.info(f"Cart cleared for user {user.uuid}")

            return Response(
                standardized_response(
                    data={
                        "order_id": str(order.order_id),
                        "installment_plan_id": installment_plan.id,
                        "duration": duration,
                        "total_amount": float(order.total_price),
                        "number_of_installments": num_installments,
                        "installment_amount": float(base_amount),
                        "first_installment_reference": first_installment.reference,
                        "authorization_url": response["data"]["authorization_url"],
                        "delivery_fee": float(order.delivery_fee) if order.delivery_fee else 0
                    },
                    message="Installment checkout initialized successfully"
                ),
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.error(f"Installment checkout error for user {user.uuid}: {str(e)}", exc_info=True)
            return Response(
                standardized_response(success=False, error=f"Installment checkout failed: {str(e)}"),
                status=status.HTTP_400_BAD_REQUEST
            )


# ----------------------
# Installment Plan Views
# ----------------------
class InstallmentPlanListView(generics.ListAPIView):
    """List all installment plans for authenticated user or all for admin"""
    serializer_class = InstallmentPlanSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="list_installment_plans",
        operation_summary="List Installment Plans",
        operation_description="Retrieve all installment plans. Customers see their own; admins see all.",
        tags=["Installments"],
        responses={
            200: InstallmentPlanSerializer(many=True),
            401: openapi.Response("Unauthorized"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return InstallmentPlan.objects.all().order_by("-created_at")
        return InstallmentPlan.objects.filter(order__customer=user).order_by("-created_at")


class InstallmentPlanDetailView(generics.RetrieveAPIView):
    """Get details of a specific installment plan"""
    serializer_class = InstallmentPlanSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    @swagger_auto_schema(
        operation_id="retrieve_installment_plan",
        operation_summary="Get Installment Plan Details",
        operation_description="Retrieve details of a specific installment plan including all payments.",
        tags=["Installments"],
        responses={
            200: InstallmentPlanSerializer,
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return InstallmentPlan.objects.all()
        return InstallmentPlan.objects.filter(order__customer=user)


class InstallmentPaymentListView(generics.ListAPIView):
    """List installment payments for a specific plan"""
    serializer_class = InstallmentPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="list_installment_payments",
        operation_summary="List Installment Payments",
        operation_description="Retrieve all payment records for a specific installment plan.",
        tags=["Installments"],
        responses={
            200: InstallmentPaymentSerializer(many=True),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        plan_id = self.kwargs.get("plan_id")
        user = self.request.user
        
        if user.is_staff:
            return InstallmentPayment.objects.filter(
                installment_plan_id=plan_id
            ).order_by("payment_number")
        
        return InstallmentPayment.objects.filter(
            installment_plan_id=plan_id,
            installment_plan__order__customer=user
        ).order_by("payment_number")


class InitializeInstallmentPaymentView(APIView):
    """Initialize payment for a specific installment (for subsequent payments 2, 3, etc.)"""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="init_installment_payment",
        operation_summary="Initialize Installment Payment",
        operation_description="""Initialize payment for a subsequent installment (payment 2, 3, etc.).
        
Only works for PENDING installments that haven't been paid yet.""",
        tags=["Installments"],
        request_body=InitializeInstallmentPaymentSerializer,
        responses={
            201: openapi.Response("Payment initialized", schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'authorization_url': openapi.Schema(type=openapi.TYPE_STRING),
                    'amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'reference': openapi.Schema(type=openapi.TYPE_STRING),
                    'payment_number': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'installment_plan_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                }
            )),
            400: openapi.Response("Missing fields or already paid"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def post(self, request):
        # Validate request data using serializer
        serializer = InitializeInstallmentPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                standardized_response(success=False, error=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        plan_id = serializer.validated_data['plan_id']
        payment_number = serializer.validated_data['payment_number']

        try:
            installment = InstallmentPayment.objects.select_related(
                'installment_plan__order'
            ).get(
                installment_plan_id=plan_id,
                payment_number=payment_number
            )
        except InstallmentPayment.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Installment not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify user owns this plan
        if installment.installment_plan.order.customer != request.user and not request.user.is_staff:
            return Response(
                standardized_response(success=False, error="Forbidden"),
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if already paid
        if installment.status == InstallmentPayment.PaymentStatus.PAID:
            return Response(
                standardized_response(success=False, error="This installment is already paid"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Initialize Paystack payment
        paystack = Paystack()
        try:
            response = paystack.initialize_payment(
                email=request.user.email,
                amount=installment.amount,
                reference=installment.reference,
                callback_url=settings.PAYSTACK_CALLBACK_URL
            )
        except Exception as e:
            return Response(
                standardized_response(success=False, error=f"Paystack error: {str(e)}"),
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            standardized_response(
                data={
                    "authorization_url": response["data"]["authorization_url"],
                    "amount": float(installment.amount),
                    "reference": installment.reference,
                    "payment_number": payment_number,
                    "installment_plan_id": plan_id
                },
                message="Installment payment initialized successfully"
            ),
            status=status.HTTP_201_CREATED
        )


class VerifyInstallmentPaymentView(APIView):
    """Verify and process an installment payment"""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [InstallmentVerificationThrottle]

    @swagger_auto_schema(
        operation_id="verify_installment_payment",
        operation_summary="Verify Installment Payment",
        operation_description="""Verify an installment payment with Paystack and mark it as PAID.
        
If all installments are paid, automatically credits vendor wallets.""",
        tags=["Installments"],
        manual_parameters=[
            openapi.Parameter('reference', openapi.IN_QUERY, description='Payment reference', type=openapi.TYPE_STRING, required=True),
        ],
        responses={
            200: openapi.Response("Payment verified", schema=InstallmentPaymentSerializer()),
            400: openapi.Response("Invalid payment or amount mismatch"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def get(self, request):
        reference = request.query_params.get("reference")
        if not reference:
            return Response(
                standardized_response(success=False, error="Reference required"),
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            installment = InstallmentPayment.objects.select_related(
                "installment_plan__order"
            ).get(reference=reference)
        except InstallmentPayment.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Payment not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        if installment.installment_plan.order.customer != request.user and not request.user.is_staff:
            return Response(
                standardized_response(success=False, error="Forbidden"),
                status=status.HTTP_403_FORBIDDEN
            )

        paystack = Paystack()
        resp = paystack.verify_payment(reference)
        data = resp.get("data", {})

        if data.get("status") != "success":
            return Response(
                standardized_response(success=False, error="Payment not successful"),
                status=status.HTTP_400_BAD_REQUEST
            )

        if data.get("currency") != EXPECTED_CURRENCY:
            return Response(
                standardized_response(success=False, error="Invalid currency"),
                status=status.HTTP_400_BAD_REQUEST
            )

        paid_amount = Decimal(data["amount"]) / Decimal(100)
        if paid_amount != installment.amount:
            return Response(
                standardized_response(success=False, error="Amount mismatch"),
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            installment = InstallmentPayment.objects.select_for_update().get(pk=installment.pk)
            
            if installment.status == InstallmentPayment.PaymentStatus.PAID:
                return Response(
                    standardized_response(
                        data=InstallmentPaymentSerializer(installment).data,
                        message="Payment already verified"
                    )
                )

            # Mark installment as paid
            installment.mark_as_paid()
            
            # Check if all installments are paid
            plan = InstallmentPlan.objects.select_for_update().get(pk=installment.installment_plan.pk)
            if plan.is_fully_paid():
                # Mark order as PAID when all installments are received
                # Vendors will be credited when order is DELIVERED, not here
                plan.order.status = Order.Status.PAID
                plan.order.save(update_fields=['status'])

        return Response(
            standardized_response(
                data=InstallmentPaymentSerializer(installment).data,
                message="Installment payment verified successfully"
            )
        )


# ----------------------
# Installment Webhook
# ----------------------
@method_decorator(csrf_exempt, name="dispatch")
class InstallmentWebhookView(APIView):
    """Handle Paystack webhook for installment payments"""
    permission_classes = []

    @swagger_auto_schema(
        operation_id="webhook_installment_payment",
        operation_summary="Paystack Webhook for Installment Payments",
        operation_description="""Webhook endpoint for Paystack to notify about installment payment status.
        
Signature verification: HMAC-SHA512
No authentication required (webhook signature validation instead)""",
        tags=["Webhooks"],
        security=[],
        responses={
            200: openapi.Response("Webhook processed"),
            403: openapi.Response("Invalid signature"),
        },
    )
    def post(self, request):
        signature = request.headers.get("x-paystack-signature", "")
        computed = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(computed, signature):
            return Response(status=403)

        data = request.data.get("data", {})
        reference = data.get("reference")

        if not reference:
            return Response({"status": "ok"})

        try:
            installment = InstallmentPayment.objects.select_for_update().get(reference=reference)
        except InstallmentPayment.DoesNotExist:
            return Response({"status": "ok"})

        paystack = Paystack()
        verify = paystack.verify_payment(reference)
        pdata = verify.get("data", {})

        if pdata.get("status") != "success":
            return Response({"status": "ok"})

        if pdata.get("currency") != EXPECTED_CURRENCY:
            return Response({"status": "ok"})

        paid_amount = Decimal(pdata["amount"]) / Decimal(100)
        if paid_amount != installment.amount:
            return Response({"status": "ok"})

        with transaction.atomic():
            if installment.status != InstallmentPayment.PaymentStatus.PAID:
                installment.mark_as_paid()
                
                # Mark order as PAID when all installments are paid
                plan = InstallmentPlan.objects.select_for_update().get(pk=installment.installment_plan.pk)
                if plan.is_fully_paid():
                    # Vendors are credited when order is DELIVERED, not when payments are complete
                    plan.order.status = Order.Status.PAID
                    plan.order.save(update_fields=['status'])

        return Response({"status": "ok"})


# ----------------------
# Payment verification
# ----------------------
class SecureVerifyPaymentView(APIView):
    throttle_classes = [PaymentVerificationThrottle]
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_id="verify_payment",
        operation_summary="Verify Single Payment",
        operation_description="""Verify a one-time (non-installment) payment with Paystack.
        
Verifies payment status and credits vendor wallets on success.
Accepts both GET (from Paystack redirects) and POST requests.

GET requests from Paystack redirects will auto-authenticate using the payment's owner.
Use the 'reference' or 'trxref' query parameter.""",
        tags=["Payments"],
        manual_parameters=[
            openapi.Parameter('reference', openapi.IN_QUERY, description='Payment reference', type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('trxref', openapi.IN_QUERY, description='Paystack transaction reference (alternative)', type=openapi.TYPE_STRING, required=False),
        ],
        responses={
            200: openapi.Response("Payment verified", schema=PaymentSerializer()),
            400: openapi.Response("Invalid payment or currency mismatch"),
            404: openapi.Response("Payment not found"),
        },
    )
    def _verify_payment(self, request, reference):
        """Helper method to verify payment (shared by GET and POST)"""
        if not reference:
            return Response(
                standardized_response(success=False, error="reference or trxref parameter required"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate reference format
        serializer = VerifyPaymentSerializer(data={'reference': reference})
        if not serializer.is_valid():
            return Response(
                standardized_response(success=False, error="Invalid reference format"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            payment = Payment.objects.select_related("order").get(reference=reference)
        except Payment.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Payment not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # For GET requests from Paystack redirects, auto-authenticate with payment owner
        # For POST requests with user auth, verify ownership
        if request.user and request.user.is_authenticated:
            if payment.order.customer != request.user and not request.user.is_staff:
                return Response(
                    standardized_response(success=False, error="Forbidden"),
                    status=status.HTTP_403_FORBIDDEN
                )

        paystack = Paystack()
        try:
            resp = paystack.verify_payment(reference)
        except Exception as e:
            return Response(
                standardized_response(success=False, error=f"Paystack verification failed: {str(e)}"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = resp.get("data", {})

        if data.get("status") != "success":
            return Response(
                standardized_response(success=False, error="Payment not successful"),
                status=status.HTTP_400_BAD_REQUEST
            )

        if data.get("currency") != EXPECTED_CURRENCY:
            return Response(
                standardized_response(success=False, error="Invalid currency"),
                status=status.HTTP_400_BAD_REQUEST
            )

        paid_amount = Decimal(data["amount"]) / Decimal(100)
        if paid_amount != payment.amount:
            return Response(
                standardized_response(success=False, error="Amount mismatch"),
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.verified:
                return Response(
                    standardized_response(
                        data=PaymentSerializer(payment).data,
                        message="Payment already verified"
                    )
                )

            payment.mark_as_successful()
            # Note: Vendors are credited when order is DELIVERED, not when payment is received
            # This maintains the available vs pending balance flow

        return Response(
            standardized_response(
                data=PaymentSerializer(payment).data,
                message="Payment verified successfully"
            )
        )

    def get(self, request):
        """Handle GET requests (Paystack redirect callback)"""
        # Support both 'reference' and 'trxref' parameters from Paystack
        reference = request.query_params.get("reference") or request.query_params.get("trxref")
        return self._verify_payment(request, reference)

    def post(self, request):
        """Handle POST requests"""
        reference = request.data.get("reference") or request.query_params.get("reference") or request.query_params.get("trxref")
        return self._verify_payment(request, reference)

# ----------------------
# Paystack webhook
# ----------------------
@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(APIView):
    permission_classes = []

    @swagger_auto_schema(
        operation_id="webhook_payment",
        operation_summary="Paystack Webhook for Single Payments",
        operation_description="""Webhook endpoint for Paystack to notify about single payment status.
        
Signature verification: HMAC-SHA512
No authentication required (webhook signature validation instead)""",
        tags=["Webhooks"],
        security=[],
        responses={
            200: openapi.Response("Webhook processed"),
            403: openapi.Response("Invalid signature"),
        },
    )
    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        signature = request.headers.get("x-paystack-signature", "")
        computed = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(computed, signature):
            logger.warning("Webhook signature verification failed")
            return Response(status=403)

        data = request.data.get("data", {})
        reference = data.get("reference")

        if not reference:
            logger.warning("Webhook received without reference")
            return Response({"status": "ok"})

        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(reference=reference)
            except Payment.DoesNotExist:
                logger.warning(f"Payment not found for reference: {reference}")
                return Response({"status": "ok"})

            try:
                paystack = Paystack()
                verify = paystack.verify_payment(reference)
                pdata = verify.get("data", {})
            except Exception as e:
                # Transient error - log and queue for retry
                # Paystack will retry the webhook, so we can safely return 200
                logger.error(f"Error verifying payment {reference}: {str(e)}", exc_info=True)
                TransactionLog.objects.create(
                    order=payment.order,
                    action=TransactionLog.Action.WEBHOOK_PROCESSED,
                    level=TransactionLog.Level.ERROR,
                    message=f"Webhook verification error for payment {reference}: {str(e)}",
                    amount=payment.amount,
                    metadata={"reference": reference, "error": str(e)}
                )
                return Response({"status": "ok"})

            # Validate payment status
            if pdata.get("status") != "success":
                logger.info(f"Payment {reference} not successful: {pdata.get('status')}")
                TransactionLog.objects.create(
                    order=payment.order,
                    action=TransactionLog.Action.PAYMENT_FAILED,
                    level=TransactionLog.Level.WARNING,
                    message=f"Payment {reference} failed with status: {pdata.get('status')}",
                    amount=payment.amount,
                    metadata={"reference": reference, "paystack_status": pdata.get('status')}
                )
                return Response({"status": "ok"})

            if pdata.get("currency") != EXPECTED_CURRENCY:
                logger.error(f"Currency mismatch for payment {reference}: expected {EXPECTED_CURRENCY}, got {pdata.get('currency')}")
                TransactionLog.objects.create(
                    order=payment.order,
                    action=TransactionLog.Action.PAYMENT_FAILED,
                    level=TransactionLog.Level.ERROR,
                    message=f"Currency mismatch for payment {reference}",
                    amount=payment.amount,
                    metadata={"reference": reference, "expected_currency": EXPECTED_CURRENCY, "received_currency": pdata.get('currency')}
                )
                return Response({"status": "ok"})

            paid_amount = Decimal(pdata["amount"]) / Decimal(100)
            if paid_amount != payment.amount:
                logger.error(f"Amount mismatch for payment {reference}: expected {payment.amount}, got {paid_amount}")
                TransactionLog.objects.create(
                    order=payment.order,
                    action=TransactionLog.Action.PAYMENT_FAILED,
                    level=TransactionLog.Level.ERROR,
                    message=f"Amount mismatch for payment {reference}",
                    amount=payment.amount,
                    metadata={"reference": reference, "expected_amount": str(payment.amount), "received_amount": str(paid_amount)}
                )
                return Response({"status": "ok"})

            if not payment.verified:
                payment.mark_as_successful()
                # Log successful payment
                TransactionLog.objects.create(
                    order=payment.order,
                    action=TransactionLog.Action.PAYMENT_RECEIVED,
                    level=TransactionLog.Level.SUCCESS,
                    message=f"Payment {reference} received and verified (₦{paid_amount})",
                    related_user=payment.order.customer,
                    amount=paid_amount,
                    metadata={"reference": reference, "paystack_status": pdata.get('status')}
                )
                logger.info(f"Payment verified successfully: {reference} (Amount: ₦{paid_amount})")
                # Note: Vendors are credited when order is DELIVERED, not when payment is received
                # This maintains the available vs pending balance flow

        return Response({"status": "ok"})

# ----------------------
# Refund management
# ----------------------
class RefundListView(generics.ListAPIView):
    serializer_class = RefundSerializer
    permission_classes = [IsAdmin]
    queryset = Refund.objects.select_related("payment", "payment__order").order_by("-created_at")

    @swagger_auto_schema(
        operation_id="list_refunds",
        operation_summary="List Refund Requests",
        operation_description="Retrieve all refund requests (admin only).",
        tags=["Refunds"],
        responses={
            200: RefundSerializer(many=True),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RefundDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RefundSerializer
    permission_classes = [IsAdmin]
    queryset = Refund.objects.select_related("payment", "payment__order")

    @swagger_auto_schema(
        operation_id="retrieve_refund",
        operation_summary="Get Refund Details",
        operation_description="Retrieve details of a specific refund request (admin only).",
        tags=["Refunds"],
        responses={
            200: RefundSerializer,
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_id="update_refund",
        operation_summary="Approve or Reject Refund",
        operation_description="""Update refund status: approve to credit customer wallet, or reject.
        
Request body: {"action": "APPROVE" or "REJECT", "rejection_reason": "optional"}""",
        tags=["Refunds"],
        request_body=RefundActionSerializer,
        responses={
            200: RefundSerializer,
            400: openapi.Response("Already processed or invalid action"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def patch(self, request, *args, **kwargs):
        # Validate request data using serializer
        serializer = RefundActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                standardized_response(success=False, error=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        refund = self.get_object()
        action = serializer.validated_data['action']
        rejection_reason = serializer.validated_data.get('rejection_reason', 'Not provided')
        
        return self.process_refund_action(refund, action, rejection_reason, request)

    def process_refund_action(self, refund, action, rejection_reason, request):
        import logging
        logger = logging.getLogger(__name__)
        
        if refund.status != Refund.Status.PENDING:
            return Response(
                standardized_response(success=False, error="Already processed"),
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            if action == "APPROVE":
                order = refund.payment.order
                customer = order.customer
                
                # Credit customer wallet with refund amount
                wallet, _ = Wallet.objects.select_for_update().get_or_create(user=customer)
                wallet.credit(refund.refunded_amount, source=f"Refund {refund.payment.reference}")
                
                # Reverse vendor commissions if order was delivered and vendors were credited
                commission_reversal_amount = Decimal("0.00")
                vendors_affected = []
                
                if order.status == Order.Status.DELIVERED and order.vendors_credited:
                    # Calculate and reverse commissions for each vendor
                    for item in order.order_items.all():
                        vendor = item.product.store
                        if vendor:
                            # Commission is 10% of item subtotal
                            commission_amount = item.item_subtotal * PLATFORM_COMMISSION
                            commission_reversal_amount += commission_amount
                            
                            # Debit vendor wallet (reverse the credit they received)
                            vendor_wallet, _ = Wallet.objects.select_for_update().get_or_create(user=vendor)
                            try:
                                vendor_wallet.debit(commission_amount, source=f"Commission Reversal - Refund {refund.payment.reference}")
                                vendors_affected.append({
                                    "vendor_id": vendor.id,
                                    "vendor_email": vendor.email,
                                    "commission_reversed": str(commission_amount)
                                })
                                
                                # Log commission reversal
                                TransactionLog.objects.create(
                                    order=order,
                                    action=TransactionLog.Action.COMMISSION_DEDUCTED,
                                    level=TransactionLog.Level.SUCCESS,
                                    message=f"Commission reversed for vendor {vendor.email}: ₦{commission_amount} (Order refunded)",
                                    related_user=vendor,
                                    amount=-commission_amount,
                                    metadata={
                                        "vendor_id": vendor.id,
                                        "vendor_email": vendor.email,
                                        "commission_amount": str(commission_amount),
                                        "reason": "Refund Approval",
                                        "refund_id": refund.id
                                    }
                                )
                                
                                logger.info(
                                    f"Commission reversed for vendor {vendor.email}: ₦{commission_amount} | "
                                    f"Reason: Order refund {order.order_id}"
                                )
                                
                            except ValueError as e:
                                logger.error(f"Failed to debit vendor {vendor.email}: {str(e)}")
                                # Continue with other vendors if one fails
                                pass
                    
                    refund.commission_reversed = True
                
                # Mark refund as approved
                refund.status = Refund.Status.APPROVED
                refund.processed_at = timezone.now()
                refund.save()
                
                # Log refund approval
                TransactionLog.objects.create(
                    order=order,
                    action=TransactionLog.Action.REFUND_APPROVED,
                    level=TransactionLog.Level.SUCCESS,
                    message=f"Refund approved for order {order.order_id}: ₦{refund.refunded_amount}. Commissions reversed: ₦{commission_reversal_amount}",
                    related_user=customer,
                    amount=refund.refunded_amount,
                    metadata={
                        "refund_id": refund.id,
                        "order_id": str(order.order_id),
                        "customer_email": customer.email,
                        "commission_reversed": str(commission_reversal_amount),
                        "vendors_affected": vendors_affected
                    }
                )
                
                logger.info(
                    f"Refund approved: Order {order.order_id} | Amount: ₦{refund.refunded_amount} | "
                    f"Commission Reversed: ₦{commission_reversal_amount}"
                )

                return Response(standardized_response(
                    success=True,
                    message="Refund approved",
                    data={
                        "refund_id": refund.id,
                        "status": refund.status,
                        "customer_credited": float(refund.refunded_amount),
                        "commission_reversed": float(commission_reversal_amount),
                        "vendors_affected_count": len(vendors_affected),
                        "vendors_affected": vendors_affected
                    }
                ))

            elif action == "REJECT":
                refund.status = Refund.Status.REJECTED
                refund.processed_at = timezone.now()
                refund.save()
                
                # Log refund rejection
                TransactionLog.objects.create(
                    order=refund.payment.order,
                    action=TransactionLog.Action.REFUND_REJECTED,
                    level=TransactionLog.Level.WARNING,
                    message=f"Refund rejected for order {refund.payment.order.order_id}: ₦{refund.refunded_amount}",
                    related_user=refund.payment.order.customer,
                    amount=refund.refunded_amount,
                    metadata={
                        "refund_id": refund.id,
                        "order_id": str(refund.payment.order.order_id),
                        "reason": rejection_reason
                    }
                )
                
                logger.info(f"Refund rejected: Order {refund.payment.order.order_id} | Amount: ₦{refund.refunded_amount}")
                
                return Response(standardized_response(
                    success=True,
                    message="Refund rejected",
                    data=RefundSerializer(refund).data
                ))
            
            return Response(
                standardized_response(success=False, error="Invalid action. Use 'APPROVE' or 'REJECT'"),
                status=status.HTTP_400_BAD_REQUEST
            )

# ----------------------
# Wallet Management
# ----------------------
class CustomerWalletView(generics.RetrieveAPIView):
    """
    Retrieve current customer's wallet balance and recent transactions.
    """
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="get_customer_wallet",
        operation_summary="Get Customer Wallet",
        operation_description="Retrieve authenticated customer's wallet balance and transaction history.",
        tags=["Wallet"],
        responses={
            200: WalletSerializer,
            401: openapi.Response("Unauthorized"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet


class WalletTransactionListView(generics.ListAPIView):
    """
    List wallet transactions for the authenticated customer.
    """
    serializer_class = WalletTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_id="list_wallet_transactions",
        operation_summary="List Wallet Transactions",
        operation_description="Retrieve all wallet transactions (credits/debits) for authenticated customer.",
        tags=["Wallet"],
        responses={
            200: WalletTransactionSerializer(many=True),
            401: openapi.Response("Unauthorized"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        wallet = get_object_or_404(Wallet, user=self.request.user)
        return wallet.transactions.all().order_by('-created_at')


class AdminWalletListView(generics.ListAPIView):
    """
    Admin endpoint to list all wallets (for monitoring/reporting).
    """
    queryset = Wallet.objects.select_related('user').order_by('-updated_at')
    serializer_class = WalletSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ['user__email']
    search_fields = ['user__email', 'user__username']

    @swagger_auto_schema(
        operation_id="list_all_wallets",
        operation_summary="List All Wallets",
        operation_description="Retrieve all customer wallets for monitoring (admin only). Supports filtering by email.",
        tags=["Wallet"],
        manual_parameters=[
            openapi.Parameter('user__email', openapi.IN_QUERY, description='Filter by user email', type=openapi.TYPE_STRING),
            openapi.Parameter('search', openapi.IN_QUERY, description='Search by email or username', type=openapi.TYPE_STRING),
        ],
        responses={
            200: WalletSerializer(many=True),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ----------------------
# Receipt/Export endpoint
# ----------------------
class OrderReceiptView(generics.RetrieveAPIView):
    """
    Retrieve order receipt/invoice details for display or export.
    Includes all granular financial details:
    - subtotal (sum of items before fees)
    - delivery_fee
    - discount (if any)
    - total_price (final amount paid)
    - payment_method (e.g., "Paystack", "Card")
    - transaction_reference (payment reference)
    """
    serializer_class = OrderReceiptSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    lookup_field = 'order_id'
    lookup_url_kwarg = 'order_id'

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(customer=self.request.user)

    @swagger_auto_schema(
        operation_id="order_receipt",
        operation_summary="Get Order Receipt",
        operation_description="""Retrieve order receipt/invoice with granular financial details.
        
Returns:
- subtotal: Sum of all items before fees
- delivery_fee: Shipping/delivery cost
- discount: Applied discount amount
- total_price: Final amount paid
- payment_method: Gateway used (e.g., Paystack)
- transaction_reference: Payment reference ID
- order_items: List of purchased items
- shipping_address: Delivery address
- tracking_number: For order tracking""",
        tags=["Orders"],
        responses={
            200: OrderReceiptSerializer,
            404: openapi.Response("Order not found"),
            403: openapi.Response("Permission denied"),
        },
    )
    def get(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(order)
        return Response(standardized_response(data=serializer.data))


# ----------------------
# Commission Analytics (Admin Only)
# ----------------------
class CommissionAnalyticsView(APIView):
    """
    Admin endpoint to view platform commission metrics and analytics.
    Provides insights into earnings, vendor commissions, and pending commissions.
    """
    permission_classes = [IsAdmin]

    @swagger_auto_schema(
        operation_id="commission_analytics",
        operation_summary="Commission Analytics Dashboard",
        operation_description="""Get comprehensive commission analytics for platform owner.
        
Metrics include:
- Total commission earned (all time)
- Commission by time period (day, week, month)
- Commission by vendor
- Pending commission (from paid but not delivered orders)
- Total delivered orders count
- Average commission per order""",
        tags=["Analytics"],
        request_body=CommissionAnalyticsQuerySerializer,
        manual_parameters=[
            openapi.Parameter('period', openapi.IN_QUERY, description='Time period: all, day, week, month, year', type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description='Filter by specific vendor ID', type=openapi.TYPE_INTEGER, required=False),
        ],
        responses={
            200: CommissionAnalyticsResponseSerializer(),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def get(self, request):
        import logging
        from django.db.models import Sum, Count, F, Q
        from datetime import datetime, timedelta
        
        logger = logging.getLogger(__name__)
        
        # Validate query parameters using serializer
        serializer = CommissionAnalyticsQuerySerializer(data={
            'period': request.query_params.get('period', 'all'),
            'vendor_id': request.query_params.get('vendor_id')
        })
        
        if not serializer.is_valid():
            return Response(
                standardized_response(success=False, error=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            period = serializer.validated_data['period']
            vendor_id = serializer.validated_data.get('vendor_id')
            
            # Define time filter based on period
            now = timezone.now()
            time_filter = Q()
            
            if period == 'day':
                time_filter = Q(delivered_at__date=now.date())
                period_label = "Today"
            elif period == 'week':
                week_start = now - timedelta(days=now.weekday())
                time_filter = Q(delivered_at__gte=week_start)
                period_label = "This Week"
            elif period == 'month':
                time_filter = Q(delivered_at__year=now.year, delivered_at__month=now.month)
                period_label = "This Month"
            elif period == 'year':
                time_filter = Q(delivered_at__year=now.year)
                period_label = "This Year"
            else:  # 'all'
                period_label = "All Time"
            
            # Get delivered orders (only delivered orders generate commissions)
            delivered_orders = Order.objects.filter(
                status=Order.Status.DELIVERED,
                vendors_credited=True,
            )
            
            if time_filter:
                delivered_orders = delivered_orders.filter(time_filter)
            
            # Calculate total commission from delivered orders
            total_commission = Decimal("0.00")
            commission_by_vendor = {}
            
            for order in delivered_orders:
                for item in order.order_items.all():
                    commission = item.item_subtotal * PLATFORM_COMMISSION
                    total_commission += commission
                    
                    vendor = item.product.store
                    if vendor:
                        if vendor.id not in commission_by_vendor:
                            commission_by_vendor[vendor.id] = {
                                "vendor_id": vendor.id,
                                "vendor_email": vendor.email,
                                "vendor_name": getattr(vendor, 'store_name', vendor.email),
                                "total_commission": Decimal("0.00"),
                                "order_count": 0,
                            }
                        commission_by_vendor[vendor.id]["total_commission"] += commission
                        commission_by_vendor[vendor.id]["order_count"] += 1
            
            # Filter by vendor if specified
            if vendor_id:
                commission_by_vendor = {
                    vid: data for vid, data in commission_by_vendor.items()
                    if vid == vendor_id
                }
                if not commission_by_vendor:
                    return Response(
                        standardized_response(
                            success=False,
                            error=f"No commission data found for vendor {vendor_id}"
                        ),
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Convert Decimal to float for JSON serialization
            commission_by_vendor_list = [
                {
                    "vendor_id": data["vendor_id"],
                    "vendor_email": data["vendor_email"],
                    "vendor_name": data["vendor_name"],
                    "total_commission": float(data["total_commission"]),
                    "order_count": data["order_count"],
                    "average_commission_per_order": float(data["total_commission"] / data["order_count"]) if data["order_count"] > 0 else 0.00,
                }
                for data in sorted(
                    commission_by_vendor.values(),
                    key=lambda x: x["total_commission"],
                    reverse=True
                )
            ]
            
            # Calculate pending commission (paid orders not yet delivered)
            pending_orders = Order.objects.filter(
                status=Order.Status.PAID,
                payment_status='PAID',
                vendors_credited=False  # Not yet credited means commission is pending
            )
            
            pending_commission = Decimal("0.00")
            for order in pending_orders:
                for item in order.order_items.all():
                    pending_commission += item.item_subtotal * PLATFORM_COMMISSION
            
            # Get top vendors by commission
            top_vendors = sorted(
                commission_by_vendor_list,
                key=lambda x: x["total_commission"],
                reverse=True
            )[:10]
            
            # Calculate statistics
            delivered_count = delivered_orders.count()
            average_commission = float(total_commission / delivered_count) if delivered_count > 0 else 0.00
            
            analytics_data = {
                "period": period_label,
                "summary": {
                    "total_commission_earned": float(total_commission),
                    "pending_commission": float(pending_commission),
                    "total_commission_including_pending": float(total_commission + pending_commission),
                    "delivered_orders_count": delivered_count,
                    "pending_orders_count": pending_orders.count(),
                    "average_commission_per_order": average_commission,
                    "unique_vendors": len(commission_by_vendor),
                },
                "by_vendor": commission_by_vendor_list,
                "top_vendors": top_vendors,
                "commission_rate": "10%",
            }
            
            logger.info(
                f"Commission analytics retrieved | Period: {period_label} | "
                f"Total Commission: ₦{total_commission} | Pending: ₦{pending_commission}"
            )
            
            return Response(standardized_response(
                success=True,
                data=analytics_data
            ))
        
        except Exception as e:
            logger.error(f"Error retrieving commission analytics: {str(e)}", exc_info=True)
            return Response(
                standardized_response(
                    success=False,
                    error=f"Error retrieving analytics: {str(e)}"
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Export for URL inclusion
__all__ = [
    'OrderListCreateView', 'OrderDetailView', 'OrderReceiptView',
    'OrderItemListCreateView', 'OrderItemDetailView',
    'TransactionLogListView',
    'CheckoutView', 'SecureVerifyPaymentView', 'PaystackWebhookView',
    'RefundListView', 'RefundDetailView',
    'CustomerWalletView', 'WalletTransactionListView', 'AdminWalletListView',
    'InstallmentCheckoutView', 'InstallmentPlanListView', 'InstallmentPlanDetailView',
    'InstallmentPaymentListView', 'InitializeInstallmentPaymentView', 'VerifyInstallmentPaymentView', 'InstallmentWebhookView',
    'CommissionAnalyticsView'
]