from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

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


admin.site.register(CustomUser, CustomUserAdmin)
