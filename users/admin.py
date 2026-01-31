from django.contrib import admin
from .models import Vendor, Customer, BusinessAdmin, Notification, DeliveryAgent, PaymentPIN, PayoutRequest, AdminPayoutProfile


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
    list_display = ('recipient', 'title', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('recipient__email', 'title', 'message')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Notification Details', {
            'fields': ('recipient', 'title', 'message')
        }),
        ('Status', {
            'fields': ('is_read', 'created_at')
        }),
    )


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
