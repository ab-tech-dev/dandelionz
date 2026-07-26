"""Admin endpoints for refund-abuse review: surface flagged customers, never auto-block."""

import logging

from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.core.permissions import IsBusinessAdmin
from authentication.core.response import standardized_response
from transactions import refund_flagging

logger = logging.getLogger(__name__)
User = get_user_model()


def _customer_brief(user):
    return {
        'uuid': str(user.uuid),
        'email': user.email,
        'full_name': getattr(user, 'full_name', '') or '',
    }


class AdminFlaggedCustomersView(APIView):
    """List customers whose refund behaviour currently warrants review, most-refunded first."""
    permission_classes = [IsAuthenticated, IsBusinessAdmin]

    def get(self, request):
        flagged = refund_flagging.flagged_customers()
        results = [
            {
                **_customer_brief(row['user']),
                'paid_orders': row['paid_orders'],
                'refund_count': row['refund_count'],
                'refund_rate': row['refund_rate'],
            }
            for row in flagged
        ]
        return Response(standardized_response(data={'count': len(results), 'results': results}))


class AdminCustomerRefundProfileView(APIView):
    """One customer's refund profile and whether they warrant review."""
    permission_classes = [IsAuthenticated, IsBusinessAdmin]

    def get(self, request, uuid):
        user = User.objects.filter(uuid=uuid, role=User.Role.CUSTOMER).first()
        if user is None:
            return Response(
                standardized_response(success=False, error="Customer not found"), status=404
            )
        profile = refund_flagging.refund_profile(user)
        return Response(standardized_response(data={**_customer_brief(user), **profile}))


class AdminReviewRefundFlagView(APIView):
    """
    Mark a flagged customer as reviewed. Snoozes the flag at their current refund count, so it
    only re-raises if they refund more. This is the whole enforcement: a human decision, no block.
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]

    def post(self, request, uuid):
        user = User.objects.filter(uuid=uuid, role=User.Role.CUSTOMER).first()
        if user is None:
            return Response(
                standardized_response(success=False, error="Customer not found"), status=404
            )
        customer = getattr(user, 'customer_profile', None)
        if customer is None:
            return Response(
                standardized_response(success=False, error="Customer profile not found"), status=404
            )

        profile = refund_flagging.refund_profile(user)
        customer.refund_flag_reviewed_count = profile['refund_count']
        customer.save(update_fields=['refund_flag_reviewed_count'])

        # Recompute so needs_review reflects the clear we just applied.
        profile = refund_flagging.refund_profile(user)
        return Response(standardized_response(
            data={**_customer_brief(user), **profile}, message="Marked as reviewed"
        ))
