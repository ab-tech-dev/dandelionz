from decimal import Decimal
from django.db import transaction
from users.models import Vendor, Customer
from transactions.models import Wallet, TransactionLog, Order
from transactions.models import Payment


class PayoutService:

    @staticmethod
    def calculate_payout(user):
        """
        Calculate the withdrawable payout for a user.
        For vendors: only completed/delivered order earnings are included
        For customers: wallet balance (referral earnings)
        """
        total = Decimal("0")

        # Vendor payout - only from delivered orders
        if hasattr(user, "vendor_profile"):
            vendor = user.vendor_profile
            # Use the new method that calculates available balance from delivered orders
            total = vendor.get_available_balance()

        # Customer referral payout
        elif hasattr(user, "customer_profile"):
            wallet = getattr(user, "wallet", None)
            if wallet:
                total = wallet.balance

        return total
    
    @staticmethod
    def get_pending_balance(user):
        """
        Get pending balance for a user (orders paid but not yet delivered).
        For vendors: earnings from SHIPPED orders
        For customers: 0 (no pending balance concept)
        """
        if hasattr(user, "vendor_profile"):
            vendor = user.vendor_profile
            return vendor.get_pending_balance()
        
        return Decimal("0")

    @staticmethod
    @transaction.atomic
    def execute_payout(user, amount):
        """Execute a payout to the user's wallet"""
        TransactionLog.objects.create(
            order=None,
            message=f"Payout of {amount} credited to {user.email}",
            level="INFO"
        )
