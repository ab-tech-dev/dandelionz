from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

from .models import Vendor, Customer, BusinessAdmin
# Assuming you have other related models like PayoutRequest, VendorEarning, etc.


# ----------------------------
# Base user data (common fields)
# ----------------------------
class UserBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'phone_number',
            'profile_picture',
            'role',
            'is_verified',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'email', 'role', 'is_verified', 'is_active', 'created_at', 'updated_at']


# --------------------------------------
# CUSTOMER PROFILE & CUSTOMER-SIDE Serializer
# --------------------------------------
class CustomerProfileSerializer(serializers.ModelSerializer):
    user = UserBaseSerializer(read_only=True)

    class Meta:
        model = Customer
        fields = [
            'user',
            'shipping_address',
            'city',
            'country',
            'postal_code',
            'loyalty_points',
        ]

        read_only_fields = ['loyalty_points']


class CustomerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'shipping_address',
            'city',
            'country',
            'postal_code',
        ]


# --------------------------------------
# VENDOR PROFILE & VENDOR-SIDE Serializer
# --------------------------------------
class VendorProfileSerializer(serializers.ModelSerializer):
    user = UserBaseSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = [
            'user',
            'store_name',
            'store_description',
            'business_registration_number',
            'address',
            'bank_name',
            'account_number',
            'recipient_code',
            'is_verified_vendor',
        ]
        read_only_fields = ['is_verified_vendor']


class VendorProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = [
            'store_name',
            'store_description',
            'address',
            'bank_name',
            'account_number',
        ]


# Example of serializer for vendor payout request (you need a model for this)
class VendorPayoutRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    bank_name = serializers.CharField(max_length=100)
    account_number = serializers.CharField(max_length=20)

    def validate_amount(self, value):
        # Example: ensure vendor has enough balance
        vendor = self.context['request'].user.vendor_profile
        if value > vendor.get_available_balance():
            raise serializers.ValidationError("Insufficient balance for payout")
        return value


# --------------------------------------
# BUSINESS ADMIN PROFILE & Admin-Side Serializer
# --------------------------------------
class BusinessAdminProfileSerializer(serializers.ModelSerializer):
    user = UserBaseSerializer(read_only=True)

    class Meta:
        model = BusinessAdmin
        fields = [
            'user',
            'position',
            'can_manage_vendors',
            'can_manage_orders',
            'can_manage_payouts',
            'can_manage_inventory',
        ]


class BusinessAdminProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessAdmin
        fields = [
            'position',
            'can_manage_vendors',
            'can_manage_orders',
            'can_manage_payouts',
            'can_manage_inventory',
        ]


# --------------------------------------
# ADMIN USER MANAGEMENT Serializer
# (for business admin to manage other users)
# --------------------------------------
class AdminUserManagementSerializer(serializers.ModelSerializer):
    # For listing or editing any user (vendor/customer)
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'phone_number',
            'role',
            'is_verified',
            'is_active',
            'created_at',
            'updated_at',
            'profile',  # vendor/customer/business-admin profile serialized dynamically
        ]
        read_only_fields = ['id', 'email', 'role', 'created_at', 'updated_at']

    def get_profile(self, obj):
        if obj.role == User.Role.VENDOR and hasattr(obj, 'vendor_profile'):
            return VendorProfileSerializer(obj.vendor_profile).data
        elif obj.role == User.Role.CUSTOMER and hasattr(obj, 'customer_profile'):
            return CustomerProfileSerializer(obj.customer_profile).data
        elif obj.role == User.Role.BUSINESS_ADMIN and hasattr(obj, 'business_admin_profile'):
            return BusinessAdminProfileSerializer(obj.business_admin_profile).data
        return None


# --------------------------------------
# Example: Vendor Earnings / Transaction Serializer
# (you’d build this if you have a VendorEarning or Payout model)
# --------------------------------------
class VendorEarningSerializer(serializers.Serializer):
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_payout = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_out = serializers.DecimalField(max_digits=12, decimal_places=2)
    # maybe list of recent orders, etc.


# Test / Example: Approval Serializer (admin approves vendor)
class VendorApprovalSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    approve = serializers.BooleanField()

    def validate_vendor_id(self, value):
        try:
            vendor = Vendor.objects.get(id=value)
        except Vendor.DoesNotExist:
            raise serializers.ValidationError("Vendor does not exist")
        return value



# users/serializers.py
from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    recipient_email = serializers.EmailField(source='recipient.email', read_only=True)
    recipient_name = serializers.CharField(source='recipient.full_name', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id',
            'recipient',
            'recipient_email',
            'recipient_name',
            'title',
            'message',
            'is_read',
            'created_at'
        ]
        read_only_fields = ['id', 'recipient_email', 'recipient_name', 'created_at']


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
