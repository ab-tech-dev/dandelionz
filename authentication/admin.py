from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ngettext
from django.contrib.admin.utils import model_ngettext
from .models import CustomUser, Referral

class CustomUserAdmin(UserAdmin):
    model = CustomUser

    list_display = ('email', 'role', 'is_staff', 'is_active', 'is_verified')
    list_filter = ('role', 'is_staff', 'is_active', 'is_verified')

    # These fields are displayed but NEVER editable (prevents admin crash)
    readonly_fields = ('last_login', 'created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        
        ('Personal Info', {
            'fields': ('full_name', 'phone_number', 'profile_picture')
        }),

        ('Permissions', {
            'fields': ('role', 'is_verified', 'is_active', 'is_staff', 'is_superuser')
        }),

        ('Referral', {
            'fields': ('referral_code',),
            'classes': ('collapse',)
        }),

        ('Important Dates', {
            'fields': ('last_login', 'created_at', 'updated_at')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role', 'is_staff', 'is_superuser'),
        }),
    )

    ordering = ('email',)

    def save_model(self, request, obj, form, change):
        # Hash raw password when creating a new user
        raw_password = form.cleaned_data.get("password")
        if raw_password and not change:
            obj.set_password(raw_password)

        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        """
        Override delete to allow superusers to delete users and their related objects.
        This allows cascade deletion of related Wallet and other objects.
        """
        super().delete_model(request, obj)

    actions = ['delete_selected']

    def delete_selected(self, request, queryset):
        """
        Override the default delete_selected action to bypass permission checks
        on related objects (like Wallet). This allows superusers to delete users
        and their cascaded related objects without permission errors.
        """
        # Delete each user individually, which will cascade to Wallet
        deleted_count = 0
        for obj in queryset:
            obj.delete()
            deleted_count += 1
        
        # Display success message
        self.message_user(
            request,
            ngettext(
                "%d custom user was successfully deleted.",
                "%d custom users were successfully deleted.",
                deleted_count,
            )
            % deleted_count,
        )

    delete_selected.short_description = "Delete selected custom users"


admin.site.register(CustomUser, CustomUserAdmin)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred_user', 'bonus_awarded', 'bonus_amount', 'created_at')
    list_filter = ('bonus_awarded', 'created_at')
    search_fields = ('referrer__email', 'referred_user__email')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Referral Information', {
            'fields': ('referrer', 'referred_user')
        }),
        ('Bonus Details', {
            'fields': ('bonus_awarded', 'bonus_amount')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
