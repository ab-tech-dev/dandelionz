from django.contrib import admin
from .models import Vendor, Customer, BusinessAdmin, DeliveryAgent, PaymentPIN, PayoutRequest, AdminPayoutProfile
from .notification_models import Notification


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'user', 'is_verified_vendor', 'business_registration_number')
    list_filter = ('is_verified_vendor',)
    search_fields = ('user__email', 'user__full_name', 'store_name')
    readonly_fields = ('user',)
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Store Details', {
            'fields': ('store_name', 'store_description', 'is_verified_vendor')
        }),
        ('Business Information', {
            'fields': ('business_registration_number', 'address')
        }),
        ('Banking Details', {
            'fields': ('bank_name', 'account_number', 'recipient_code')
        }),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'country', 'loyalty_points')
    list_filter = ('country', 'city')
    search_fields = ('user__email', 'user__full_name', 'city')
    readonly_fields = ('user',)
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Address Details', {
            'fields': ('shipping_address', 'city', 'country', 'postal_code')
        }),
        ('Loyalty', {
            'fields': ('loyalty_points',)
        }),
    )


@admin.register(BusinessAdmin)
class BusinessAdminAdmin(admin.ModelAdmin):
    list_display = ('user', 'position', 'can_manage_vendors', 'can_manage_orders')
    list_filter = ('can_manage_vendors', 'can_manage_orders', 'can_manage_payouts', 'can_manage_inventory')
    search_fields = ('user__email', 'user__full_name', 'position')
    readonly_fields = ('user',)
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'position')
        }),
        ('Permissions', {
            'fields': ('can_manage_vendors', 'can_manage_orders', 'can_manage_payouts', 'can_manage_inventory')
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'priority', 'is_read', 'created_at')
    list_filter = ('is_read', 'priority', 'category', 'created_at', 'was_sent_websocket', 'was_sent_email')
    search_fields = ('user__email', 'title', 'message', 'category')
    readonly_fields = ('created_at', 'updated_at', 'read_at', 'id')
    fieldsets = (
        ('Notification Details', {
            'fields': ('id', 'user', 'notification_type', 'title', 'message', 'description')
        }),
        ('Metadata', {
            'fields': ('category', 'priority', 'metadata')
        }),
        ('Action', {
            'fields': ('action_url', 'action_text')
        }),
        ('Related Object', {
            'fields': ('related_object_type', 'related_object_id')
        }),
        ('Status', {
            'fields': ('is_read', 'is_archived', 'is_deleted')
        }),
        ('Delivery Tracking', {
            'fields': ('was_sent_websocket', 'was_sent_email', 'was_sent_push', 'send_attempts')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'read_at', 'expires_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """Notifications are created programmatically"""
        return False


@admin.register(DeliveryAgent)
class DeliveryAgentAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__email', 'user__full_name', 'phone')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(PaymentPIN)
class PaymentPINAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_default', 'created_at', 'updated_at')
    list_filter = ('is_default', 'created_at')
    search_fields = ('user__email', 'user__full_name')
    readonly_fields = ('user', 'pin_hash', 'created_at', 'updated_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('PIN Status', {
            'fields': ('is_default',)
        }),
        ('PIN Hash', {
            'fields': ('pin_hash',),
            'description': 'PIN is hashed and never displayed. Set new PIN via user settings.',
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """PaymentPINs are created automatically; prevent manual creation."""
        return False


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'vendor', 'amount', 'status', 'created_at', 'processed_at')
    list_filter = ('status', 'created_at', 'processed_at')
    search_fields = ('reference', 'user__email', 'vendor__store_name', 'account_number')
    readonly_fields = ('reference', 'user', 'vendor', 'created_at', 'processed_at')
    fieldsets = (
        ('Payout Information', {
            'fields': ('reference', 'user', 'vendor', 'amount')
        }),
        ('Recipient Details', {
            'fields': ('bank_name', 'account_number', 'account_name', 'recipient_code')
        }),
        ('Status', {
            'fields': ('status', 'rejection_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['retry_payouts']

    def _net_charged(self, queryset):
        """
        How much each selected payout has actually taken out of its wallet, net.

        Net, not "was there a debit": a transfer that Paystack rejects synchronously is
        debited and then reversed (see AdminWalletViewSet.withdraw), leaving both a
        WITHDRAWAL debit and a WITHDRAWAL_REVERSAL credit. Such a payout has been made
        whole, so retrying it would send money a second time - an existence check would
        wave it straight through.

        One grouped query for the whole selection rather than one per row.
        """
        from collections import defaultdict
        from decimal import Decimal

        from django.db.models import Sum
        from transactions.models import LedgerEntry

        net = defaultdict(lambda: Decimal('0.00'))
        rows = (
            LedgerEntry.objects
            .filter(payout_request__in=queryset)
            .values('payout_request_id', 'direction')
            .annotate(total=Sum('amount'))
        )
        for row in rows:
            amount = row['total'] or Decimal('0.00')
            if row['direction'] == LedgerEntry.Direction.DEBIT:
                net[row['payout_request_id']] += amount
            else:
                net[row['payout_request_id']] -= amount
        return net

    def retry_payouts(self, request, queryset):
        from decimal import Decimal

        from users.services.payout_service import PayoutService
        from transactions.models import LedgerEntry

        success_count = 0
        failed_count = 0

        net_charged = self._net_charged(queryset)

        # Payouts older than the ledger itself cannot be judged this way. backfill_ledger
        # only adopts an opening balance per wallet; it never reconstructs per-payout
        # entries, so every pre-ledger payout has nothing linked to it. Blocking those
        # would take away the retry action for exactly the historical failures it exists
        # to fix, so the check applies only from the point the ledger starts.
        ledger_start = (
            LedgerEntry.objects.order_by('created_at')
            .values_list('created_at', flat=True)
            .first()
        )

        for payout in queryset:
            if payout.status in ['failed', 'processing']:
                covered_by_ledger = (
                    ledger_start is not None
                    and payout.created_at is not None
                    and payout.created_at >= ledger_start
                )
                if covered_by_ledger and net_charged[payout.pk] <= Decimal('0.00'):
                    # Either never debited, or debited and already reversed. Both mean the
                    # wallet still holds this money, so paying it out now would create the
                    # discrepancy rather than settle it.
                    failed_count += 1
                    self.message_user(
                        request,
                        f"Payout {payout.reference} has no outstanding ledger debit - the "
                        f"wallet was either never charged for it or has already been "
                        f"refunded. Not retried. Reconcile the wallet before paying this "
                        f"out.",
                        level='ERROR',
                    )
                    continue

                success, msg = PayoutService.process_external_transfer(payout)
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    self.message_user(request, f"Payout {payout.reference} failed: {msg}", level='ERROR')
            else:
                self.message_user(request, f"Payout {payout.reference} is not in a failed/processing state.", level='WARNING')
                
        if success_count > 0:
            self.message_user(request, f"Successfully retried {success_count} payout(s).", level='SUCCESS')
            
    retry_payouts.short_description = "Retry failed Paystack transfers"


@admin.register(AdminPayoutProfile)
class AdminPayoutProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'account_number', 'updated_at')
    list_filter = ('updated_at',)
    search_fields = ('user__email', 'user__full_name', 'bank_name', 'account_number')
    readonly_fields = ('updated_at',)
    fieldsets = (
        ('Admin Information', {
            'fields': ('user',)
        }),
        ('Banking Details', {
            'fields': ('bank_name', 'account_number', 'account_name', 'recipient_code')
        }),
        ('Timestamps', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    fieldsets = (
        ('Admin Information', {
            'fields': ('user',)
        }),
        ('Banking Details', {
            'fields': ('bank_name', 'account_number', 'account_name', 'recipient_code')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
