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
from transactions.models import Wallet 
from users.models import Notification

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
        order = serializer.save(customer=self.request.user)
        order.update_total()

        # Notify all vendors involved in the order
        product_vendors = set()
        for item in order.order_items.all():
            if item.vendor:
                product_vendors.add(item.vendor)

        for vendor in product_vendors:
            Notification.objects.create(
                recipient=vendor,
                title="New Order Received",
                message=f"You have received a new order {order.order_id} from {order.customer.email}."
            )


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
        # After logging the initialization
        TransactionLog.objects.create(order=order, message=f"Payment initialized (ref={payment.reference})", level="INFO")

        # Create notification for customer
        Notification.objects.create(
            recipient=order.customer,
            title="Payment Initialized",
            message=f"Your payment of {payment.amount} for order {order.order_id} has been initialized. Please complete the payment."
        )

        return Response({
            "authorization_url": resp.get("data", {}).get("authorization_url"),
            "access_code": resp.get("data", {}).get("access_code"),
            "reference": payment.reference,
            "amount": float(payment.amount)
        })

# ----------------------
# Payment verification (client or admin can call to confirm)
# ----------------------
from django.db import transaction
from decimal import Decimal

PLATFORM_COMMISSION = Decimal("0.10")  # 10% commission

class SecureVerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reference = request.query_params.get("reference")
        if not reference:
            return Response({"detail": "reference required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.select_related('order').get(reference=reference)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        p = Paystack()
        try:
            resp = p.verify_payment(reference)
        except Exception as exc:
            TransactionLog.objects.create(order=payment.order, message=f"Paystack verify error: {exc}", level="ERROR")
            return Response({"detail": "Verification failed"}, status=500)

        if not resp.get("status") or resp.get("data", {}).get("status") != "success":
            return Response({"detail": "Payment not successful according to Paystack", "raw": resp}, status=400)

        data = resp.get("data", {})
        paid_amount = Decimal(data.get("amount", 0)) / Decimal(100)
        if paid_amount != payment.amount:
            TransactionLog.objects.create(order=payment.order, message="Amount mismatch on verify", level="WARNING")
            return Response({"detail": "Amount mismatch"}, status=400)

        if payment.verified:
            return Response({"detail": "Payment already verified", "order_id": str(payment.order.order_id)})

        try:
            with transaction.atomic():
                payment.mark_as_successful()
                TransactionLog.objects.create(order=payment.order, message=f"Payment verified (ref={reference})", level="INFO")

                Notification.objects.create(
                    recipient=payment.order.customer,
                    title="Payment Successful",
                    message=f"Your payment of {payment.amount} for order {payment.order.order_id} has been successfully verified."
                )

                for item in payment.order.order_items.all():
                    vendor = item.vendor
                    if vendor:
                        full_amount = item.item_subtotal
                        vendor_amount = full_amount * (Decimal("1.00") - PLATFORM_COMMISSION)

                        wallet, _ = Wallet.objects.get_or_create(user=vendor)
                        wallet.credit(vendor_amount, source=f"Order {payment.order.order_id} - {item.product.name}")

                        Notification.objects.create(
                            recipient=vendor,
                            title="Payment Received",
                            message=f"Your wallet has been credited with {vendor_amount} for order {payment.order.order_id} (product: {item.product.name})."
                        )

                        # Optional: log platform commission
                        TransactionLog.objects.create(
                            order=payment.order,
                            message=f"Platform commission {full_amount - vendor_amount} deducted from order {payment.order.order_id}, item {item.product.name}",
                            level="INFO"
                        )
        except Exception as exc:
            TransactionLog.objects.create(order=payment.order, message=f"Payment verification failed during wallet crediting: {exc}", level="ERROR")
            return Response({"detail": "Payment verification failed"}, status=500)

        return Response({"detail": "Payment verified", "order_id": str(payment.order.order_id)})


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    permission_classes = []

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
                payment = Payment.objects.select_related('order').get(reference=reference)
            except Payment.DoesNotExist:
                TransactionLog.objects.create(message=f"Webhook: payment not found for ref={reference}", level="WARNING", order=None)
                return Response({"status": "ok"})

            if payment.verified:
                return Response({"status": "ok"})  # already processed

            try:
                with transaction.atomic():
                    payment.mark_as_successful()
                    TransactionLog.objects.create(order=payment.order, message="Webhook: payment success", level="INFO")

                    Notification.objects.create(
                        recipient=payment.order.customer,
                        title="Payment Successful",
                        message=f"Your payment of {payment.amount} for order {payment.order.order_id} has been successfully processed via Paystack."
                    )

                    for item in payment.order.order_items.all():
                        vendor = item.vendor
                        if vendor:
                            full_amount = item.item_subtotal
                            vendor_amount = full_amount * (Decimal("1.00") - PLATFORM_COMMISSION)

                            wallet, _ = Wallet.objects.get_or_create(user=vendor)
                            wallet.credit(vendor_amount, source=f"Order {payment.order.order_id} - {item.product.name}")

                            Notification.objects.create(
                                recipient=vendor,
                                title="Payment Received",
                                message=f"Your wallet has been credited with {vendor_amount} for order {payment.order.order_id} (product: {item.product.name})."
                            )

                            TransactionLog.objects.create(
                                order=payment.order,
                                message=f"Platform commission {full_amount - vendor_amount} deducted from order {payment.order.order_id}, item {item.product.name}",
                                level="INFO"
                            )
            except Exception as exc:
                TransactionLog.objects.create(order=payment.order, message=f"Webhook processing failed: {exc}", level="ERROR")
                return Response({"status": "failed"}, status=500)

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


from django.db import transaction
from decimal import Decimal


class RefundDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or process a refund (approve/reject).
    Only admins can update the refund status.
    Refunds are verifiable via logs and wallet transactions.
    """
    queryset = Refund.objects.select_related('payment', 'payment__order')
    serializer_class = RefundSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'id'

    def update(self, request, *args, **kwargs):
        refund = self.get_object()
        action = request.data.get("action", "").upper()

        # Ensure payment exists and is successful
        if not refund.payment.verified or refund.payment.status != 'SUCCESS':
            return Response({"detail": "Refund cannot be processed: Payment not verified."}, status=400)

        if refund.status != "PENDING":
            return Response({"detail": "Refund already processed."}, status=status.HTTP_400_BAD_REQUEST)

        customer = refund.payment.order.customer

        try:
            with transaction.atomic():
                if action == "APPROVE":
                    refund.status = "APPROVED"
                    refund.processed_at = timezone.now()
                    refund.save(update_fields=["status", "processed_at"])

                    # Credit full refund amount to customer
                    wallet, _ = Wallet.objects.get_or_create(user=customer)
                    wallet.credit(refund.refunded_amount, source=f"Refund for payment {refund.payment.reference}")

                    TransactionLog.objects.create(
                        order=refund.payment.order,
                        message=f"Refund approved for payment ref={refund.payment.reference}, amount credited: {refund.refunded_amount}",
                        level="INFO"
                    )

                    # Debit vendors for their share (90% of each item subtotal)
                    for item in refund.payment.order.order_items.all():
                        vendor = item.vendor
                        if vendor:
                            vendor_debit = item.item_subtotal * (Decimal("1.00") - PLATFORM_COMMISSION)
                            vendor_wallet, _ = Wallet.objects.get_or_create(user=vendor)
                            vendor_wallet.debit(vendor_debit, source=f"Refund for order {refund.payment.order.order_id} - {item.product.name}")

                            TransactionLog.objects.create(
                                order=refund.payment.order,
                                message=f"Vendor {vendor.email} debited {vendor_debit} for refunded item {item.product.name}",
                                level="INFO"
                            )

                            Notification.objects.create(
                                recipient=vendor,
                                title="Refund Processed",
                                message=f"{vendor_debit} has been deducted from your wallet for refunded item {item.product.name} in order {refund.payment.order.order_id}."
                            )

                    # Notify customer
                    Notification.objects.create(
                        recipient=customer,
                        title="Refund Approved",
                        message=f"Your refund of {refund.refunded_amount} for order {refund.payment.order.order_id} has been approved and credited to your wallet."
                    )

                    return Response({"detail": "Refund approved and processed successfully."})

                elif action == "REJECT":
                    refund.status = "REJECTED"
                    refund.processed_at = timezone.now()
                    refund.save(update_fields=["status", "processed_at"])

                    TransactionLog.objects.create(
                        order=refund.payment.order,
                        message=f"Refund rejected for payment ref={refund.payment.reference}",
                        level="WARNING"
                    )

                    Notification.objects.create(
                        recipient=customer,
                        title="Refund Rejected",
                        message=f"Your refund request for order {refund.payment.order.order_id} has been rejected."
                    )

                    return Response({"detail": "Refund rejected successfully."})
                else:
                    return Response(
                        {"detail": "Invalid action. Use 'APPROVE' or 'REJECT'."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        except Exception as exc:
            TransactionLog.objects.create(
                order=refund.payment.order,
                message=f"Refund processing failed: {exc}",
                level="ERROR"
            )
            return Response({"detail": "Refund processing failed"}, status=500)
