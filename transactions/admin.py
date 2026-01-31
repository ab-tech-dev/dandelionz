from django.contrib import admin
from .models import (
    Order, OrderItem, Payment, ShippingAddress, TransactionLog, Refund, Wallet, 
    WalletTransaction, PayoutRecord, InstallmentPlan, InstallmentPayment,
    OrderStatusHistory, Settlement, SettlementItem, Dispute
)
from django.db.models import Sum
from datetime import timedelta
from django.utils import timezone
from django.utils.html import format_html
from authentication.models import CustomUser


class AnalyticsAdmin(admin.AdminSite):
    """
    Admin dashboard with analytics overview
    """
    site_header = "E-Commerce Admin"
    site_title = "Admin Portal"
    index_title = "Platform Analytics Dashboard"

    def index(self, request, extra_context=None):
        """Display analytics on admin index page"""
        if extra_context is None:
            extra_context = {}
        
        # Calculate analytics metrics
        total_products_sold = OrderItem.objects.aggregate(total=Sum("quantity"))["total"] or 0
        total_balance = Wallet.objects.aggregate(total=Sum("balance"))["total"] or 0
        thirty_days_ago = timezone.now() - timedelta(days=30)
        new_customers = CustomUser.objects.filter(
            role='CUSTOMER',
            created_at__gte=thirty_days_ago
        ).count()
        total_orders = Order.objects.count()
        total_revenue = Payment.objects.filter(
            status='SUCCESS',
            verified=True
        ).aggregate(total=Sum("amount"))["total"] or 0
        pending_orders = Order.objects.filter(status='PENDING').count()
        delivered_orders = Order.objects.filter(status='DELIVERED').count()

        extra_context['analytics'] = {
            'total_orders': total_orders,
            'total_revenue': f"₦{total_revenue:,.2f}",
            'total_balance': f"₦{total_balance:,.2f}",
            'total_products_sold': total_products_sold,
            'new_customers': new_customers,
            'pending_orders': pending_orders,
            'delivered_orders': delivered_orders,
        }
        
        return super().index(request, extra_context)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer', 'delivery_agent', 'status', 'total_price', 'payment_status', 'assigned_at', 'ordered_at')
    search_fields = ('order_id', 'customer__email', 'customer__username', 'delivery_agent__user__full_name')
    list_filter = ('status', 'payment_status', 'ordered_at', 'assigned_at')
    readonly_fields = ('order_id', 'ordered_at', 'updated_at', 'assigned_at')
    fieldsets = (
        ('Order Information', {
            'fields': ('order_id', 'customer', 'status', 'payment_status')
        }),
        ('Pricing', {
            'fields': ('total_price', 'delivery_fee', 'discount')
        }),
        ('Delivery', {
            'fields': ('delivery_agent', 'tracking_number', 'assigned_at')
        }),
        ('Metadata', {
            'fields': ('ordered_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'quantity', 'price_at_purchase', 'item_subtotal')
    search_fields = ('product__name', 'order__order_id')
    list_filter = ('order__ordered_at',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order', 'amount', 'status', 'verified', 'paid_at', 'created_at')
    search_fields = ('reference', 'order__order_id')
    list_filter = ('status', 'verified', 'created_at')
    readonly_fields = ('reference', 'created_at')


@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'level', 'created_at', 'message')
    list_filter = ('level', 'created_at')
    search_fields = ('order__order_id', 'message')
    readonly_fields = ('created_at',)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'status', 'refunded_amount', 'created_at', 'processed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment__reference', 'payment__order__order_id')
    readonly_fields = ('created_at',)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'updated_at')
    search_fields = ('user__email', 'user__username')
    list_filter = ('updated_at',)
    readonly_fields = ('user', 'balance', 'updated_at')
    
    def has_delete_permission(self, request, obj=None):
        """Prevent direct deletion of wallets; they should cascade delete with users."""
        return False

    def has_add_permission(self, request):
        """Wallets are created automatically on signal; prevent manual creation."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent wallet deletion to maintain data integrity."""
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'transaction_type', 'amount', 'source', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('wallet__user__email', 'source')
    readonly_fields = ('wallet', 'transaction_type', 'amount', 'source', 'created_at')

    def has_add_permission(self, request):
        """Transactions are created by wallet methods; prevent manual creation."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent transaction deletion to maintain audit trail."""
        return False


@admin.register(ShippingAddress)
class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = ('order', 'full_name', 'city', 'state', 'country')
    search_fields = ('order__order_id', 'full_name', 'email')
    list_filter = ('country', 'state')
    fieldsets = (
        ('Order', {
            'fields': ('order',)
        }),
        ('Recipient Information', {
            'fields': ('full_name', 'phone_number')
        }),
        ('Address Details', {
            'fields': ('address', 'city', 'state', 'country', 'postal_code')
        }),
    )


@admin.register(PayoutRecord)
class PayoutRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'reference', 'created_at')
    search_fields = ('user__email', 'reference')
    list_filter = ('created_at',)
    readonly_fields = ('user', 'reference', 'created_at')


# ========================
# INSTALLMENT PAYMENT ADMIN
# ========================
class InstallmentPaymentInline(admin.TabularInline):
    model = InstallmentPayment
    extra = 0
    fields = ('payment_number', 'amount', 'status', 'due_date', 'paid_at', 'reference')
    readonly_fields = ('payment_number', 'amount', 'reference', 'created_at')
    can_delete = False


@admin.register(InstallmentPlan)
class InstallmentPlanAdmin(admin.ModelAdmin):
    list_display = ('order', 'duration', 'total_amount', 'installment_amount', 'number_of_installments', 'status', 'created_at')
    list_filter = ('duration', 'status', 'created_at')
    search_fields = ('order__order_id', 'order__customer__email')
    readonly_fields = ('order', 'total_amount', 'installment_amount', 'number_of_installments', 'start_date', 'created_at', 'updated_at')
    inlines = [InstallmentPaymentInline]
    fieldsets = (
        ('Order Information', {
            'fields': ('order', 'status')
        }),
        ('Plan Details', {
            'fields': ('duration', 'total_amount', 'number_of_installments', 'installment_amount')
        }),
        ('Dates', {
            'fields': ('start_date', 'created_at', 'updated_at')
        }),
    )


@admin.register(InstallmentPayment)
class InstallmentPaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_number', 'installment_plan', 'amount', 'status', 'due_date', 'paid_at', 'created_at')
    list_filter = ('status', 'due_date', 'created_at')
    search_fields = ('reference', 'installment_plan__order__order_id')
    readonly_fields = ('reference', 'created_at', 'updated_at')
    fieldsets = (
        ('Payment Information', {
            'fields': ('installment_plan', 'payment_number', 'reference')
        }),
        ('Amount & Status', {
            'fields': ('amount', 'status')
        }),
        ('Dates', {
            'fields': ('due_date', 'paid_at', 'created_at', 'updated_at')
        }),
        ('Gateway', {
            'fields': ('gateway', 'verified')
        }),
    )


# ========================
# ORDER STATUS HISTORY ADMIN
# ========================
@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'old_status', 'new_status', 'changed_by', 'changed_at')
    list_filter = ('new_status', 'changed_at')
    search_fields = ('order__order_id', 'changed_by__email')
    readonly_fields = ('order', 'old_status', 'new_status', 'changed_by', 'changed_at', 'reason')
    fieldsets = (
        ('Order Information', {
            'fields': ('order',)
        }),
        ('Status Change', {
            'fields': ('old_status', 'new_status', 'reason')
        }),
        ('Metadata', {
            'fields': ('changed_by', 'changed_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """OrderStatusHistory is created automatically on order status changes."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion to maintain audit trail."""
        return False


# ========================
# SETTLEMENT ADMIN
# ========================
class SettlementItemInline(admin.TabularInline):
    model = SettlementItem
    extra = 0
    fields = ('vendor', 'total_sales', 'commission', 'settlement_amount', 'status')
    readonly_fields = ('vendor', 'total_sales', 'commission', 'settlement_amount')
    can_delete = False


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ('reference', 'settlement_period', 'total_amount', 'status', 'created_at', 'processed_at')
    list_filter = ('status', 'settlement_period', 'created_at')
    search_fields = ('reference', 'notes')
    readonly_fields = ('reference', 'created_at', 'processed_at')
    inlines = [SettlementItemInline]
    fieldsets = (
        ('Settlement Information', {
            'fields': ('reference', 'settlement_period', 'status')
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SettlementItem)
class SettlementItemAdmin(admin.ModelAdmin):
    list_display = ('settlement', 'vendor', 'total_sales', 'commission', 'settlement_amount', 'status')
    list_filter = ('status', 'settlement__created_at')
    search_fields = ('settlement__reference', 'vendor__store_name')
    readonly_fields = ('settlement', 'vendor', 'total_sales', 'commission', 'settlement_amount')
    fieldsets = (
        ('Settlement', {
            'fields': ('settlement', 'vendor')
        }),
        ('Financial Details', {
            'fields': ('total_sales', 'commission', 'settlement_amount')
        }),
        ('Status', {
            'fields': ('status',)
        }),
    )

    def has_add_permission(self, request):
        """SettlementItems are created automatically during settlement generation."""
        return False


# ========================
# DISPUTE ADMIN
# ========================
@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order', 'raised_by', 'status', 'severity', 'created_at', 'resolved_at')
    list_filter = ('status', 'severity', 'created_at')
    search_fields = ('reference', 'order__order_id', 'raised_by__email', 'description')
    readonly_fields = ('reference', 'created_at', 'resolved_at')
    fieldsets = (
        ('Dispute Information', {
            'fields': ('reference', 'order', 'raised_by', 'severity')
        }),
        ('Details', {
            'fields': ('title', 'description', 'status', 'resolution')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'resolved_at'),
            'classes': ('collapse',)
        }),
    )
