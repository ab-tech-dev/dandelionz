import hmac
import hashlib
import uuid
from decimal import Decimal
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
from transactions.models import Wallet, WalletTransaction
from users.models import Notification

from .models import Order, OrderItem, Payment, TransactionLog, Refund
from .serializers import (
    OrderSerializer,
    OrderItemSerializer,
    TransactionLogSerializer,
    PaymentSerializer,
    RefundSerializer,
    WalletSerializer,
    WalletTransactionSerializer
)
from .paystack import Paystack


PLATFORM_COMMISSION = Decimal("0.10")
EXPECTED_CURRENCY = "NGN"


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

        # Notify the vendor of this product
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
    permission_classes = [permissions.IsAdminUser]
    serializer_class = TransactionLogSerializer
    queryset = TransactionLog.objects.all().order_by('-created_at')

# ----------------------
# Payment initialization
# ----------------------
class SecureInitializePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id, customer=request.user)

        if order.status != Order.Status.PENDING:
            return Response({"detail": "Order already processed"}, status=400)

        calculated_total = order.calculate_total()

        reference = f"{order.order_id}-{uuid.uuid4().hex[:12]}"

        payment, created = Payment.objects.get_or_create(
            order=order,
            defaults={
                "amount": calculated_total,
                "reference": reference,
                "currency": EXPECTED_CURRENCY
            }
        )

        if not created:
            payment.amount = calculated_total
            payment.currency = EXPECTED_CURRENCY
            payment.verified = False
            payment.status = Payment.Status.PENDING
            payment.save(update_fields=["amount", "currency", "verified", "status"])

        paystack = Paystack()
        resp = paystack.initialize_payment(
            request.user.email,
            payment.amount,
            payment.reference,
            settings.PAYSTACK_CALLBACK_URL
        )

        TransactionLog.objects.create(
            order=order,
            message=f"Payment initialized ref={payment.reference}",
            level="INFO"
        )

        return Response({
            "authorization_url": resp["data"]["authorization_url"],
            "reference": payment.reference,
            "amount": float(payment.amount)
        })


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

            for item in payment.order.order_items.all():
                if not item.vendor:
                    continue

                vendor_share = item.item_subtotal * (Decimal("1.00") - PLATFORM_COMMISSION)
                wallet, _ = Wallet.objects.select_for_update().get_or_create(user=item.vendor)
                wallet.credit(vendor_share, source=f"Order {payment.order.order_id}")

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
    permission_classes = [permissions.IsAdminUser]
    filterset_fields = ['user__email']
    search_fields = ['user__email', 'user__username']


# Export for URL inclusion
__all__ = [
    'OrderListCreateView', 'OrderDetailView',
    'OrderItemListCreateView', 'OrderItemDetailView',
    'TransactionLogListView',
    'SecureInitializePaymentView', 'SecureVerifyPaymentView', 'PaystackWebhookView',
    'RefundListView', 'RefundDetailView',
    'CustomerWalletView', 'WalletTransactionListView', 'AdminWalletListView'
]
