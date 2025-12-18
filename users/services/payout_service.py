from decimal import Decimal
from django.db import transaction
from users.models import Vendor, Customer
from transactions.models import Wallet, TransactionLog
from transactions.models import Order
from transactions.models import Payment


class PayoutService:

    @staticmethod
    def calculate_payout(user):
        total = Decimal("0")

        # Vendor payout
        if hasattr(user, "vendor_profile"):
            vendor = user.vendor_profile

            orders = Order.objects.filter(
                order_items__product__store=vendor,
                payment__status="SUCCESS"
            ).distinct()

            for order in orders:
                for item in order.order_items.all():
                    if item.product.store == vendor:
                        total += item.item_subtotal * Decimal("0.90")

        # Customer referral payout
        elif hasattr(user, "customer_profile"):
            wallet = getattr(user, "wallet", None)
            if wallet:
                total = wallet.balance

        return total

    @staticmethod
    @transaction.atomic
    def execute_payout(user, amount):
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.credit(amount, source="Admin Payout")

        TransactionLog.objects.create(
            order=None,
            message=f"Payout of {amount} credited to {user.email}",
            level="INFO"
        )
