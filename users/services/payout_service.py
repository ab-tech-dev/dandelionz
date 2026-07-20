from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from users.models import Vendor, Customer, PayoutRequest, BusinessAdmin
from transactions.models import Wallet, TransactionLog, Order
from transactions.models import Payment
from transactions.paystack import Paystack
import uuid as uuid_lib
import logging

logger = logging.getLogger(__name__)


class PayoutService:

    @staticmethod
    def calculate_payout(user):
        """
        Calculate the withdrawable payout for a user.
        For vendors: only completed/delivered order earnings are included
        For customers: the withdrawable wallet bucket (referral earnings, refunds)
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
                # Not wallet.balance: the total includes the customer's own deposits, which
                # are spendable at checkout but never withdrawable to a bank. Quoting the
                # total here would advertise a payout that create_withdrawal_request
                # refuses downstream.
                total = wallet.withdrawable_balance

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
    
    @staticmethod
    def validate_withdrawal_request(user, amount):
        """
        Validate withdrawal request before processing.
        Returns: (is_valid, error_message)
        """
        # Check wallet exists and has sufficient WITHDRAWABLE balance.
        # Deliberately not wallet.balance: that total includes the user's own Paystack
        # deposits, which are spendable at checkout but must never leave as a bank transfer.
        from transactions.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=user)

        if wallet.withdrawable_balance < Decimal(str(amount)):
            return False, f"Insufficient balance. Available: ₦{wallet.withdrawable_balance:,.2f}, Requested: ₦{amount:,.2f}"

        if amount <= 0:
            return False, "Withdrawal amount must be greater than zero"

        minimum = getattr(settings, 'MIN_WITHDRAWAL_NGN', Decimal('500'))
        if Decimal(str(amount)) < minimum:
            return False, f"The minimum withdrawal amount is ₦{minimum:,.2f}"
        
        # Check if user has a non-default PIN set
        from users.models import PaymentPIN
        try:
            pin_obj = PaymentPIN.objects.get(user=user)
            if pin_obj.is_default:
                return False, "Please set a secure payment PIN in Payment Settings before you can withdraw funds. Default PIN (0000) is not allowed for security reasons."
        except PaymentPIN.DoesNotExist:
            return False, "Please set a secure payment PIN in Payment Settings before you can withdraw funds."
        
        # REMOVED: _validate_vendor_verified_earnings — wallet.balance is the source of truth.
        # Earnings are only credited to the wallet on delivery, so the balance already
        # represents verified, withdrawable funds.

        return True, None
    
    @staticmethod
    def verify_pin(user, pin):
        """
        Verify user's payment PIN.
        Returns: (is_valid, error_message)
        """
        from users.models import PaymentPIN
        try:
            pin_obj = PaymentPIN.objects.get(user=user)
            if not pin_obj.verify_pin(pin):
                return False, "Invalid PIN"
            return True, None
        except PaymentPIN.DoesNotExist:
            return False, "PIN not configured"
    
    @staticmethod
    @transaction.atomic
    def create_withdrawal_request(
        user,
        amount,
        bank_name,
        account_number,
        account_name,
        recipient_code='',
        vendor=None,
        auto_process=False,
        bank_code=''
    ):
        """
        Create a withdrawal request and debit the wallet.
        Also notifies admins about the withdrawal request.
        
        Returns: (payout_request, error_message)
        """
        try:
            # Validate amount. Repeated here rather than relying on the caller having run
            # validate_withdrawal_request - this is the only funnel every withdrawal path
            # (customer, vendor, admin) actually goes through.
            if amount <= 0:
                return None, "Amount must be greater than zero"

            minimum = getattr(settings, 'MIN_WITHDRAWAL_NGN', Decimal('500'))
            if Decimal(str(amount)) < minimum:
                return None, f"The minimum withdrawal amount is ₦{minimum:,.2f}"
            
            # Get wallet and check balance under a row lock.
            # Without the lock, two concurrent withdrawal requests could both read the same
            # balance, both pass this check, and both debit - overdrawing the wallet.
            from transactions.models import LedgerEntry, Wallet
            Wallet.objects.get_or_create(user=user)
            wallet = Wallet.objects.select_for_update().get(user=user)

            # Only withdrawable funds can be cashed out; deposits are checkout-only.
            if wallet.withdrawable_balance < Decimal(str(amount)):
                return None, f"Insufficient balance. Available: ₦{wallet.withdrawable_balance:,.2f}"

            # Create withdrawal request
            payout = PayoutRequest.objects.create(
                user=user if not vendor else None,
                vendor=vendor,
                amount=Decimal(str(amount)),
                bank_name=bank_name,
                # Snapshotted onto the request so the payout still resolves to the right
                # bank if the user edits their payout settings before it is approved.
                bank_code=bank_code,
                account_number=account_number,
                account_name=account_name,
                recipient_code=recipient_code,
                reference=f"WTH-{uuid_lib.uuid4().hex[:12].upper()}",
                status='processing' if auto_process else 'pending',
                processed_at=timezone.now() if auto_process else None,
            )

            # Debit wallet, withdrawable bucket only
            wallet.debit(
                Decimal(str(amount)),
                source=f"Withdrawal {payout.reference}",
                bucket=LedgerEntry.Bucket.WITHDRAWABLE,
                entry_type=LedgerEntry.EntryType.WITHDRAWAL,
                idempotency_key=f"withdrawal-{payout.reference}",
                payout_request=payout,
            )
            
            # Log the withdrawal request
            logger.info(f"Withdrawal request created: {payout.reference} for {user.email}, Amount: ₦{amount:,.2f}")
            
            # Notify admins
            PayoutService.notify_admins_of_withdrawal(payout, user, vendor)
            
            return payout, None
            
        except Exception as e:
            logger.error(f"Error creating withdrawal request: {str(e)}", exc_info=True)
            return None, f"Error processing withdrawal: {str(e)}"
    
    @staticmethod
    def notify_admins_of_withdrawal(payout, user, vendor):
        """
        Notify all admins when a withdrawal request is created.
        """
        try:
            from users.notification_service import NotificationService
            
            # Get all admin users
            admin_users = BusinessAdmin.objects.select_related('user').all()
            
            if vendor:
                requestor_name = vendor.store_name
                requestor_type = "Vendor"
                requestor_email = vendor.user.email
            else:
                requestor_name = user.full_name or user.email
                requestor_type = "Customer"
                requestor_email = user.email
            
            title = f"New {requestor_type} Withdrawal Request"
            message = (
                f"{requestor_name} has requested a withdrawal of ₦{payout.amount:,.2f}\n"
                f"Account: {payout.account_name}\n"
                f"Reference: {payout.reference}"
            )
            description = (
                f"Withdrawal Details:\n"
                f"Requestor: {requestor_name} ({requestor_email})\n"
                f"Amount: ₦{payout.amount:,.2f}\n"
                f"Bank: {payout.bank_name}\n"
                f"Account: {payout.account_number}\n"
                f"Account Name: {payout.account_name}\n"
                f"Reference: {payout.reference}\n"
                f"Status: {payout.status}\n"
                f"Requested At: {payout.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Send notification to each admin
            for admin in admin_users:
                NotificationService.create_notification(
                    user=admin.user,
                    title=title,
                    message=message,
                    category='withdrawal',
                    priority='high' if payout.amount > Decimal('100000') else 'normal',
                    description=description,
                    action_url=f"/admin/withdrawals/{payout.id}",
                    action_text="Review Withdrawal",
                    related_object_type='withdrawal',
                    related_object_id=str(payout.id),
                    metadata={
                        'payout_id': str(payout.id),
                        'reference': payout.reference,
                        'amount': str(payout.amount),
                        'requestor_type': requestor_type,
                        'requestor_email': requestor_email,
                    },
                    send_websocket=True,
                    send_email=True,
                )
            
            logger.info(f"Withdrawal notification sent to {admin_users.count()} admins for reference {payout.reference}")
            
        except Exception as e:
            logger.error(f"Error notifying admins of withdrawal: {str(e)}", exc_info=True)

    @staticmethod
    def _validate_vendor_verified_earnings(vendor, amount):
        """
        Ensure vendor withdrawal amount is backed by verified, delivered orders.
        """
        from transactions.models import Order, OrderItem
        from django.db.models import F, Sum, DecimalField, ExpressionWrapper

        # Block if any delivered, credited orders are tied to unverified payments
        unverified_orders = Order.objects.filter(
            order_items__product__store=vendor,
            status=Order.Status.DELIVERED,
            vendors_credited=True,
        ).exclude(payment__verified=True).distinct()

        if unverified_orders.exists():
            return False, "Withdrawal blocked: some delivered orders have unverified payments."

        subtotal_expr = ExpressionWrapper(
            F('price_at_purchase') * F('quantity'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
        subtotal = OrderItem.objects.filter(
            product__store=vendor,
            order__status=Order.Status.DELIVERED,
            order__vendors_credited=True,
            order__payment__verified=True,
        ).aggregate(total=Sum(subtotal_expr))['total'] or Decimal("0")

        # Vendor share is 90% after 10% commission
        verified_earnings = subtotal * Decimal("0.90")

        if Decimal(str(amount)) > verified_earnings:
            return False, "Withdrawal amount exceeds verified earnings."

        return True, None

    @staticmethod
    def get_or_create_paystack_recipient(profile):
        """
        Ensures a Paystack recipient_code exists for the vendor or admin profile.
        Profile can be a Vendor instance or AdminPayoutProfile instance.
        """
        if profile.recipient_code:
            return profile.recipient_code

        if not profile.bank_code or not profile.account_number:
            return None

        try:
            paystack = Paystack()
            resp = paystack.create_transfer_recipient(
                name=profile.account_name or "User Payout",
                account_number=profile.account_number,
                bank_code=profile.bank_code
            )
            if resp.get("status"):
                recipient_code = resp["data"]["recipient_code"]
                profile.recipient_code = recipient_code
                profile.save(update_fields=["recipient_code"])
                return recipient_code
        except Exception as e:
            logger.error(f"Error creating Paystack recipient for {profile}: {str(e)}")
        
        return None

    @staticmethod
    def process_external_transfer(payout_request):
        """
        Initiates the actual bank transfer via Paystack.
        Returns: (success, message/reference)
        """
        if payout_request.status != "processing":
            return False, f"Cannot process payout in {payout_request.status} state"

        recipient_code = payout_request.recipient_code
        
        # If no recipient code on request, try to get it from profile.
        # The customer_profile branch is what makes customer withdrawals completable at
        # all: without it a customer payout has no recipient code and every transfer was
        # rejected below with "No transfer recipient code available".
        if not recipient_code:
            if payout_request.vendor:
                recipient_code = PayoutService.get_or_create_paystack_recipient(payout_request.vendor)
            elif payout_request.user and hasattr(payout_request.user, "admin_payout_profile"):
                recipient_code = PayoutService.get_or_create_paystack_recipient(payout_request.user.admin_payout_profile)
            elif payout_request.user and hasattr(payout_request.user, "customer_profile"):
                recipient_code = PayoutService.get_or_create_paystack_recipient(payout_request.user.customer_profile)
        
        if not recipient_code:
            return False, "No transfer recipient code available. Verify bank details."

        try:
            paystack = Paystack()
            resp = paystack.initiate_transfer(
                amount=payout_request.amount,
                recipient_code=recipient_code,
                reference=payout_request.reference,
                reason=f"Payout {payout_request.reference}"
            )
            
            if resp.get("status"):
                # Transfer initiated successfully (often status is 'success' or 'pending' in Paystack)
                # Paystack transfer status: 'success', 'pending', 'processing', 'failed', 'reversed'
                transfer_data = resp["data"]
                payout_request.status = "successful" if transfer_data["status"] == "success" else "processing"
                payout_request.processed_at = timezone.now()
                payout_request.save()
                return True, payout_request.reference
            else:
                payout_request.status = "failed"
                payout_request.failure_reason = resp.get("message", "Unknown Paystack error")
                payout_request.save()
                return False, payout_request.failure_reason

        except Exception as e:
            logger.error(f"Paystack Transfer Exception for {payout_request.reference}: {str(e)}")
            return False, str(e)
