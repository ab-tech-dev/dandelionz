import hmac
import hashlib
from decimal import Decimal
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from authentication.core.permissions import IsVendor, IsCustomer, IsAdmin

from .models import Order, OrderItem, Payment, TransactionLog
from .serializers import (
    OrderSerializer, OrderItemSerializer, TransactionLogSerializer, PaymentSerializer
)
from .paystack import Paystack

# ----------------------
# Custom permissions
# ----------------------
class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Orders have `customer` field
        owner = getattr(obj, 'customer', None)
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
            return Order.objects.all().order_by('-ordered_at')
        return Order.objects.filter(customer=user).order_by('-ordered_at')

    def perform_create(self, serializer):
        # Keep creation simple; prefer OrderCreate flow if complex
        order = serializer.save(customer=self.request.user)
        # Ensure total is up-to-date
        order.update_total()

class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    lookup_field = 'order_id'

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(customer=user)

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
        serializer.save(order=order)
        order.update_total()

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
# Payment initialisation (secure)
# ----------------------
class SecureInitializePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        # ensure order belongs to this user
        order = get_object_or_404(Order, order_id=order_id, customer=request.user)

        if order.status != order.Status.PENDING:
            return Response({"detail": "Order already processed."}, status=status.HTTP_400_BAD_REQUEST)

        # recompute total on backend
        calculated_total = order.calculate_total()

        # create or get Payment record (idempotent behavior)
        payment, created = Payment.objects.get_or_create(order=order, defaults={"amount": calculated_total})
        # if exists but amount mismatch, fix it (or create a new reference by re-creating; here we update safely)
        if not created and payment.amount != calculated_total:
            payment.amount = calculated_total
            payment.verified = False
            payment.status = 'PENDING'
            payment.save(update_fields=['amount', 'verified', 'status'])

        # Initialize with Paystack
        p = Paystack()
        callback_url = getattr(settings, "PAYSTACK_CALLBACK_URL", None)
        if not callback_url:
            return Response({"detail": "PAYSTACK_CALLBACK_URL not configured."}, status=500)

        try:
            resp = p.initialize_payment(request.user.email, payment.amount, payment.reference, callback_url)
        except Exception as exc:
            TransactionLog.objects.create(order=order, message=f"Paystack init error: {exc}", level="ERROR")
            return Response({"detail": "Failed to initialize payment."}, status=500)

        # Log
        TransactionLog.objects.create(order=order, message=f"Payment initialized (ref={payment.reference})", level="INFO")

        return Response({
            "authorization_url": resp.get("data", {}).get("authorization_url"),
            "access_code": resp.get("data", {}).get("access_code"),
            "reference": payment.reference,
            "amount": float(payment.amount)
        })

# ----------------------
# Payment verification (client or admin can call to confirm)
# ----------------------
class SecureVerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reference = request.query_params.get("reference")
        if not reference:
            return Response({"detail": "reference required"}, status=status.HTTP_400_BAD_REQUEST)

        # find Payment; ensure it relates to this user's order or user is admin
        try:
            payment = Payment.objects.select_related('order').get(reference=reference)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        # verify with Paystack server to be safe
        p = Paystack()
        try:
            resp = p.verify_payment(reference)
        except Exception as exc:
            TransactionLog.objects.create(order=payment.order, message=f"Paystack verify error: {exc}", level="ERROR")
            return Response({"detail": "Verification failed"}, status=500)

        if not resp.get("status"):
            return Response({"detail": "Paystack verification failed", "raw": resp}, status=400)

        data = resp.get("data", {})
        if data.get("status") != "success":
            return Response({"detail": "Payment not successful according to Paystack", "raw": resp}, status=400)

        # confirm amounts match
        paid_amount = Decimal(data.get("amount", 0)) / Decimal(100)
        if paid_amount != payment.amount:
            TransactionLog.objects.create(order=payment.order, message="Amount mismatch on verify", level="WARNING")
            return Response({"detail": "Amount mismatch"}, status=400)

        if not payment.verified:
            payment.mark_as_successful()
            TransactionLog.objects.create(order=payment.order, message=f"Payment verified (ref={reference})", level="INFO")

        return Response({"detail": "Payment verified", "order_id": str(payment.order.order_id)})

# ----------------------
# Paystack webhook (HMAC signature verification)
# ----------------------
@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    permission_classes = []  # external system

    def post(self, request):
        signature = request.headers.get("x-paystack-signature", "")
        secret = settings.PAYSTACK_SECRET_KEY.encode()
        computed = hmac.new(secret, msg=request.body, digestmod=hashlib.sha512).hexdigest()

        if not hmac.compare_digest(computed, signature):
            return Response({"detail": "Invalid signature"}, status=403)

        event = request.data.get('event')
        data = request.data.get('data', {})
        reference = data.get('reference')
        if event == 'charge.success' and reference:
            try:
                payment = Payment.objects.get(reference=reference)
                if not payment.verified:
                    payment.mark_as_successful()
                    TransactionLog.objects.create(order=payment.order, message="Webhook: payment success", level="INFO")
            except Payment.DoesNotExist:
                TransactionLog.objects.create(message=f"Webhook: payment not found for ref={reference}", level="WARNING", order=None)
        return Response({"status": "ok"})



from .models import Refund, Payment, TransactionLog
from .serializers import RefundSerializer


# ----------------------
# Refund / Return Management (ADMIN ONLY)
# ----------------------
class RefundListView(generics.ListAPIView):
    """
    List all refund (return) requests — accessible only by admin users.
    """
    queryset = Refund.objects.select_related('payment', 'payment__order').order_by('-created_at')
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAdminUser]


class RefundDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or process a refund (approve/reject).
    Only admins can update the refund status.
    """
    queryset = Refund.objects.select_related('payment', 'payment__order')
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'id'

    def update(self, request, *args, **kwargs):
        refund = self.get_object()
        action = request.data.get("action", "").upper()

        if refund.status != "PENDING":
            return Response({"detail": "Refund already processed."}, status=status.HTTP_400_BAD_REQUEST)

        if action == "APPROVE":
            refund.status = "APPROVED"
            refund.processed_at = timezone.now()
            refund.save(update_fields=["status", "processed_at"])

            # Log approval
            TransactionLog.objects.create(
                order=refund.payment.order,
                message=f"Refund approved for payment ref={refund.payment.reference}",
                level="INFO",
            )
            return Response({"detail": "Refund approved successfully."})

        elif action == "REJECT":
            refund.status = "REJECTED"
            refund.processed_at = timezone.now()
            refund.save(update_fields=["status", "processed_at"])

            # Log rejection
            TransactionLog.objects.create(
                order=refund.payment.order,
                message=f"Refund rejected for payment ref={refund.payment.reference}",
                level="WARNING",
            )
            return Response({"detail": "Refund rejected successfully."})

        else:
            return Response(
                {"detail": "Invalid action. Use 'APPROVE' or 'REJECT'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
