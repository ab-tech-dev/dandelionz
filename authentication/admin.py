from django.contrib import admin
from .models import CustomUser


@admin.register(CustomUser)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_verified', 'role','created_at')
    search_fields = ('email',)
    list_filter = ('is_verified', 'is_staff')