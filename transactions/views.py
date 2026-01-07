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

# ----------------------
# Checkout Endpoint (New)
# ----------------------
class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return InstallmentPlan.objects.all()
        return InstallmentPlan.objects.filter(order__customer=user)


class InstallmentPaymentListView(generics.ListAPIView):
    """List installment payments for a specific plan"""
    serializer_class = InstallmentPaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

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


class VerifyInstallmentPaymentView(APIView):
    """Verify and process an installment payment"""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

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


class RefundDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RefundSerializer
    permission_classes = [IsAdmin]
    queryset = Refund.objects.select_related("payment", "payment__order")

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

    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet


class WalletTransactionListView(generics.ListAPIView):
    """
    List wallet transactions for the authenticated customer.
    """
    serializer_class = WalletTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

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


# Export for URL inclusion
__all__ = [
    'OrderListCreateView', 'OrderDetailView',
    'OrderItemListCreateView', 'OrderItemDetailView',
    'TransactionLogListView',
    'CheckoutView', 'SecureVerifyPaymentView', 'PaystackWebhookView',
    'RefundListView', 'RefundDetailView',
    'CustomerWalletView', 'WalletTransactionListView', 'AdminWalletListView',
    'InstallmentCheckoutView', 'InstallmentPlanListView', 'InstallmentPlanDetailView',
    'InstallmentPaymentListView', 'VerifyInstallmentPaymentView', 'InstallmentWebhookView'
]