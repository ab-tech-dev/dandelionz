"""API endpoints for paying an order's delivery fee (Paystack + wallet)."""

import logging

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from transactions import delivery_payment
from transactions.delivery_payment import DeliveryPaymentError
from transactions.models import Order, DeliveryCharge
from transactions.wallet_checkout import WalletPaymentError
from authentication.core.response import standardized_response

logger = logging.getLogger(__name__)


class InitializeDeliveryPaymentView(APIView):
    """Start paying an order's delivery fee, from wallet, card, or both."""
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        order = Order.objects.filter(order_id=order_id, customer=request.user).first()
        if order is None:
            return Response(
                standardized_response(success=False, error="Order not found"),
                status=404,
            )

        use_wallet = bool(request.data.get('use_wallet', False))
        requested_wallet = request.data.get('wallet_amount')

        from transactions.views import _get_paystack_callback_url
        try:
            result = delivery_payment.initialize_delivery_payment(
                order,
                callback_url=_get_paystack_callback_url(request),
                use_wallet=use_wallet,
                requested_wallet=requested_wallet,
            )
        except (DeliveryPaymentError, WalletPaymentError) as exc:
            return Response(standardized_response(success=False, error=str(exc)), status=400)

        return Response(standardized_response(data=result, message="Delivery payment initialized"))


class VerifyDeliveryPaymentView(APIView):
    """Verify a delivery-fee card payment and settle it."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return self._verify(request, request.query_params.get('reference'))

    def post(self, request):
        return self._verify(request, request.data.get('reference'))

    def _verify(self, request, reference):
        if not reference:
            return Response(
                standardized_response(success=False, error="reference is required"),
                status=400,
            )

        charge = DeliveryCharge.objects.filter(reference=reference).select_related('order', 'order__customer').first()
        if charge is None or charge.order.customer != request.user:
            return Response(
                standardized_response(success=False, error="Delivery payment not found"),
                status=404,
            )

        try:
            charge = delivery_payment.verify_delivery_payment(reference)
        except DeliveryPaymentError as exc:
            return Response(standardized_response(success=False, error=str(exc)), status=400)

        return Response(standardized_response(
            data={
                'reference': charge.reference,
                'status': charge.status,
                'order_id': str(charge.order.order_id),
                'delivery_fee_paid': charge.order.delivery_fee_paid,
            },
            message="Delivery payment verified",
        ))
