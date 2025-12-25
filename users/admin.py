from django.contrib import admin
from .models import Vendor, Customer, BusinessAdmin, Notification, DeliveryAgent


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
