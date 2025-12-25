from django.contrib import admin
from .models import Order, OrderItem, Payment, ShippingAddress, TransactionLog, Refund, Wallet, WalletTransaction, PayoutRecord


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer', 'status', 'total_price', 'payment_status', 'ordered_at')
    search_fields = ('order_id', 'customer__email', 'customer__username')
    list_filter = ('status', 'payment_status', 'ordered_at')
    readonly_fields = ('order_id', 'ordered_at', 'updated_at')


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
    readonly_fields = ('user', 'updated_at')

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
