import hmac
import hashlib
import uuid
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

from .models import Order, OrderItem, Payment, TransactionLog, Refund
from store.models import Cart, CartItem
from .serializers import (
    OrderSerializer,
    OrderItemSerializer,
    TransactionLogSerializer,
    PaymentSerializer,
    RefundSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
    InstallmentPlanSerializer,
    InstallmentPaymentSerializer,
    InstallmentCheckoutSerializer
)
from .paystack import Paystack
from authentication.core.response import standardized_response

PLATFORM_COMMISSION = Decimal("0.10")
EXPECTED_CURRENCY = "NGN"

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
    for item in order.order_items.all():
        vendor = item.product.store
        if not vendor:
            continue
        vendor_share = item.item_subtotal * (Decimal("1.00") - PLATFORM_COMMISSION)
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=vendor)
        wallet.credit(vendor_share, source=f"{source_prefix} {order.order_id}")

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
        operation_description="Retrieve details of a specific order.",
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
        cart = Cart.objects.filter(customer=user).first()
        if not cart:
            return Response(
                standardized_response(success=False, error="Cart is empty"),
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_items = CartItem.objects.select_related("product").filter(cart=cart)
        if not cart_items.exists():
            return Response(
                standardized_response(success=False, error="Cart has no items"),
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # 1. Create Order
            order = Order.objects.create(customer=user)

            # 2. Convert CartItems → OrderItems
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price_at_purchase=item.product.price
                )

            # 3. Calculate total
            order.update_total()

            # 4. Create or reset Payment
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

            # 5. Initialize Paystack
            paystack = Paystack()
            response = paystack.initialize_payment(
                email=user.email,
                amount=payment.amount,
                reference=payment.reference,
                callback_url=settings.PAYSTACK_CALLBACK_URL
            )

            # 6. Notify vendors
            vendors = {item.vendor for item in order.order_items.all() if item.vendor}
            for vendor in vendors:
                Notification.objects.create(
                    recipient=vendor,
                    title="New Order Received",
                    message=f"You received a new order {order.order_id}."
                )

            # 7. Clear cart
            cart_items.delete()

        return Response(
            standardized_response(
                data={
                    "order_id": order.order_id,
                    "authorization_url": response["data"]["authorization_url"],
                    "reference": payment.reference,
                    "amount": float(payment.amount)
                },
                message="Checkout initialized successfully"
            ),
            status=status.HTTP_201_CREATED
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
        cart = Cart.objects.filter(customer=user).first()
        
        if not cart:
            return Response(
                standardized_response(success=False, error="Cart is empty"),
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_items = CartItem.objects.select_related("product").filter(cart=cart)
        if not cart_items.exists():
            return Response(
                standardized_response(success=False, error="Cart has no items"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate installment duration
        serializer = InstallmentCheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                standardized_response(success=False, error=serializer.errors),
                status=status.HTTP_400_BAD_REQUEST
            )

        duration = serializer.validated_data['duration']

        with transaction.atomic():
            # 1. Create Order
            order = Order.objects.create(customer=user)

            # 2. Convert CartItems → OrderItems
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    price_at_purchase=item.product.price,
                )

            # 3. Calculate total
            order.update_total()

            # 4. Create Installment Plan
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

            # 5. Create individual installment payment records
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

            # 6. Initialize payment for first installment
            first_installment = installment_plan.installments.first()
            paystack = Paystack()
            response = paystack.initialize_payment(
                email=user.email,
                amount=first_installment.amount,
                reference=first_installment.reference,
                callback_url=settings.PAYSTACK_CALLBACK_URL
            )

            # 7. Notify vendors
            vendors = {item.product.store for item in cart_items if item.product.store}
            for vendor in vendors:
                Notification.objects.create(
                    recipient=vendor,
                    title="New Order Received (Installment)",
                    message=f"You received a new order {order.order_id} with installment plan ({duration})."
                )

            # 8. Clear cart
            cart_items.delete()

        return Response(
            standardized_response(
                data={
                    "order_id": order.order_id,
                    "installment_plan_id": installment_plan.id,
                    "duration": duration,
                    "total_amount": float(order.total_price),
                    "number_of_installments": num_installments,
                    "installment_amount": float(base_amount),
                    "first_installment_reference": first_installment.reference,
                    "authorization_url": response["data"]["authorization_url"],
                },
                message="Installment checkout initialized successfully"
            ),
            status=status.HTTP_201_CREATED
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
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'plan_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Installment plan ID'),
                'payment_number': openapi.Schema(type=openapi.TYPE_INTEGER, description='Which installment (2, 3, etc.)'),
            },
            required=['plan_id', 'payment_number']
        ),
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
        plan_id = request.data.get('plan_id')
        payment_number = request.data.get('payment_number')

        if not plan_id or not payment_number:
            return Response(
                standardized_response(success=False, error="plan_id and payment_number required"),
                status=status.HTTP_400_BAD_REQUEST
            )

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
    throttle_classes = [UserRateThrottle]

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
            
            # Credit vendor wallet for completed installments (when final payment is made)
            plan = InstallmentPlan.objects.select_for_update().get(pk=installment.installment_plan.pk)
            if plan.is_fully_paid() and not plan.vendors_credited:
                for item in plan.order.order_items.all():
                    vendor = item.product.store
                    if vendor:
                        vendor_share = item.item_subtotal * (Decimal("1.00") - PLATFORM_COMMISSION)
                        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=vendor)
                        wallet.credit(vendor_share, source=f"Order {plan.order.order_id} (Installment)")
                # Mark vendors as credited to prevent duplicate credits
                plan.vendors_credited = True
                plan.save(update_fields=['vendors_credited'])

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
                
                # Credit vendor wallet if plan is completed
                plan = InstallmentPlan.objects.select_for_update().get(pk=installment.installment_plan.pk)
                if plan.is_fully_paid() and not plan.vendors_credited:
                    credit_vendors_for_order(plan.order, source_prefix="Order (Installment)")
                    plan.vendors_credited = True
                    plan.save(update_fields=['vendors_credited'])

        return Response({"status": "ok"})


# ----------------------
# Payment verification
# ----------------------
class SecureVerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_id="verify_payment",
        operation_summary="Verify Single Payment",
        operation_description="""Verify a one-time (non-installment) payment with Paystack.
        
Verifies payment status and credits vendor wallets on success.""",
        tags=["Payments"],
        manual_parameters=[
            openapi.Parameter('reference', openapi.IN_QUERY, description='Payment reference', type=openapi.TYPE_STRING, required=True),
        ],
        responses={
            200: openapi.Response("Payment verified", schema=PaymentSerializer()),
            400: openapi.Response("Invalid payment or currency mismatch"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
        },
    )
    def get(self, request):
        reference = request.query_params.get("reference")
        if not reference:
            return Response({"detail": "reference required"}, status=400)

        payment = get_object_or_404(
            Payment.objects.select_related("order"),
            reference=reference
        )

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({"detail": "Forbidden"}, status=403)

        paystack = Paystack()
        resp = paystack.verify_payment(reference)
        data = resp.get("data", {})

        if data.get("status") != "success":
            return Response({"detail": "Payment not successful"}, status=400)

        if data.get("currency") != EXPECTED_CURRENCY:
            return Response({"detail": "Invalid currency"}, status=400)

        paid_amount = Decimal(data["amount"]) / Decimal(100)
        if paid_amount != payment.amount:
            return Response({"detail": "Amount mismatch"}, status=400)

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.verified:
                return Response({"detail": "Already verified"})

            payment.mark_as_successful()
            credit_vendors_for_order(payment.order)

        return Response({"detail": "Payment verified"})

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
            payment = Payment.objects.select_for_update().get(reference=reference)
        except Payment.DoesNotExist:
            return Response({"status": "ok"})

        paystack = Paystack()
        verify = paystack.verify_payment(reference)
        pdata = verify.get("data", {})

        if pdata.get("status") != "success":
            return Response({"status": "ok"})

        if pdata.get("currency") != EXPECTED_CURRENCY:
            return Response({"status": "ok"})

        paid_amount = Decimal(pdata["amount"]) / Decimal(100)
        if paid_amount != payment.amount:
            return Response({"status": "ok"})

        with transaction.atomic():
            if not payment.verified:
                payment.mark_as_successful()
                credit_vendors_for_order(payment.order)

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
        
Request body: {"action": "APPROVE" or "REJECT"}""",
        tags=["Refunds"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'action': openapi.Schema(type=openapi.TYPE_STRING, enum=['APPROVE', 'REJECT']),
            },
            required=['action']
        ),
        responses={
            200: RefundSerializer,
            400: openapi.Response("Already processed or invalid action"),
            401: openapi.Response("Unauthorized"),
            403: openapi.Response("Forbidden"),
            404: openapi.Response("Not Found"),
        },
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        refund = self.get_object()
        action = request.data.get("action", "").upper()

        if refund.status != Refund.Status.PENDING:
            return Response({"detail": "Already processed"}, status=400)

        with transaction.atomic():
            if action == "APPROVE":
                wallet, _ = Wallet.objects.select_for_update().get_or_create(
                    user=refund.payment.order.customer
                )
                wallet.credit(refund.refunded_amount, source=f"Refund {refund.payment.reference}")

                refund.status = Refund.Status.APPROVED
                refund.processed_at = timezone.now()
                refund.save()

                return Response({"detail": "Refund approved"})

            if action == "REJECT":
                refund.status = Refund.Status.REJECTED
                refund.processed_at = timezone.now()
                refund.save()
                return Response({"detail": "Refund rejected"})

        return Response({"detail": "Invalid action"}, status=400)

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
    Includes all order information needed for receipts, invoices, and tracking.
    """
    serializer_class = OrderSerializer
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
        operation_description="Retrieve order receipt/invoice details including items, shipping address, payment info, and tracking number. Can be used for display or export to PDF.",
        tags=["Orders"],
        responses={
            200: OrderSerializer,
            404: openapi.Response("Order not found"),
            403: openapi.Response("Permission denied"),
        },
    )
    def get(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(order)
        return Response(standardized_response(data=serializer.data))


# Export for URL inclusion
__all__ = [
    'OrderListCreateView', 'OrderDetailView', 'OrderReceiptView',
    'OrderItemListCreateView', 'OrderItemDetailView',
    'TransactionLogListView',
    'CheckoutView', 'SecureVerifyPaymentView', 'PaystackWebhookView',
    'RefundListView', 'RefundDetailView',
    'CustomerWalletView', 'WalletTransactionListView', 'AdminWalletListView',
    'InstallmentCheckoutView', 'InstallmentPlanListView', 'InstallmentPlanDetailView',
    'InstallmentPaymentListView', 'InitializeInstallmentPaymentView', 'VerifyInstallmentPaymentView', 'InstallmentWebhookView'
]