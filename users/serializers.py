from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import (
    Vendor,
    Customer,
    BusinessAdmin,
    Notification
)

User = get_user_model()


# =====================================================
# BASE USER SERIALIZER (READ-ONLY USER DATA)
# =====================================================
class UserBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'uuid',
            'email',
            'full_name',
            'phone_number',
            'profile_picture',
            'role',
            'referral_code',
            'is_verified',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

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
            'business_registration_number',
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
        user = self.context['request'].user

        if not hasattr(user, 'vendor_profile'):
            raise serializers.ValidationError("Vendor profile not found")

        vendor = user.vendor_profile

        if not hasattr(vendor, 'get_available_balance'):
            raise serializers.ValidationError("Balance system not configured")

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
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'uuid',
            'email',
            'full_name',
            'phone_number',
            'role',
            'referral_code',
            'is_verified',
            'is_active',
            'created_at',
            'updated_at',
            'profile',
        ]
        read_only_fields = [
            'uuid',
            'email',
            'role',
            'created_at',
            'updated_at',
        ]

    def get_profile(self, obj):
        # Use getattr with default to avoid AttributeError
        role = getattr(obj, 'role', None)

        if role == User.Role.VENDOR and hasattr(obj, 'vendor_profile'):
            return VendorProfileSerializer(obj.vendor_profile).data

        if role == User.Role.CUSTOMER and hasattr(obj, 'customer_profile'):
            return CustomerProfileSerializer(obj.customer_profile).data

        # Check BusinessAdmin differently if obj is BusinessAdmin
        if isinstance(obj, BusinessAdmin) and hasattr(obj, 'business_admin_profile'):
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

# Test / Example: Approval Serializer (admin approves vendor)
class VendorApprovalSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()
    approve = serializers.BooleanField()

    def validate_user_uuid(self, value):
        try:
            user = User.objects.get(uuid=value, role=User.Role.VENDOR)
        except User.DoesNotExist:
            raise serializers.ValidationError("Vendor user does not exist")

        if not hasattr(user, 'vendor_profile'):
            raise serializers.ValidationError("Vendor profile not found")

        return value




# users/serializers.py
class NotificationSerializer(serializers.ModelSerializer):
    recipient_email = serializers.EmailField(
        source='recipient.email',
        read_only=True
    )
    recipient_name = serializers.CharField(
        source='recipient.full_name',
        read_only=True
    )

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
            'created_at',
        ]
        read_only_fields = [
            'id',
            'recipient_email',
            'recipient_name',
            'created_at',
        ]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)


from rest_framework import serializers
from transactions.models import Order


class OrderActionSerializer(serializers.Serializer):
    order_uuid = serializers.UUIDField()

    def validate_order_uuid(self, value):
        if not Order.objects.filter(uuid=value).exists():
            raise serializers.ValidationError("Order not found")
        return value


from rest_framework import serializers
from store.models import Product


class AdminProductUpdateSerializer(serializers.Serializer):
    product_uuid = serializers.UUIDField()
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_product_uuid(self, value):
        if not Product.objects.filter(uuid=value).exists():
            raise serializers.ValidationError("Product does not exist")
        return value


from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class VendorKYCSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()

    def validate_user_uuid(self, value):
        user = User.objects.filter(uuid=value, role=User.Role.VENDOR).first()
        if not user or not hasattr(user, "vendor_profile"):
            raise serializers.ValidationError("Vendor not found")
        return value


from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class SuspendUserSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()
    suspend = serializers.BooleanField()

    def validate_user_uuid(self, value):
        if not User.objects.filter(uuid=value).exists():
            raise serializers.ValidationError("User not found")
        return value



from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class TriggerPayoutSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()

    def validate_user_uuid(self, value):
        if not User.objects.filter(uuid=value).exists():
            raise serializers.ValidationError("User does not exist")
        return value



class AdminAnalyticsSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_orders = serializers.IntegerField()
    delivered_orders = serializers.IntegerField()



class AdminFinancePaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user = serializers.CharField(source="user.email")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()

class AdminFinancePayoutSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()


class AdminOrdersSummarySerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    shipped = serializers.IntegerField()
    delivered = serializers.IntegerField()

class AdminOrderActionSerializer(serializers.Serializer):
    order_uuid = serializers.UUIDField()

class AdminOrderActionResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField(required=False, allow_blank=True)

from rest_framework import serializers

class AdminProductListSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    store = serializers.CharField(source='store.store_name')
    is_active = serializers.BooleanField()

class AdminProductUpdateRequestSerializer(serializers.Serializer):
    product_slug = serializers.SlugField()
    name = serializers.CharField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_active = serializers.BooleanField(required=False)

class AdminProductActionResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField(required=False)
    message = serializers.CharField(required=False, allow_blank=True)



from rest_framework import serializers

class AdminVendorListSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField(source='user.uuid')
    email = serializers.EmailField(source='user.email')
    store_name = serializers.CharField()
    is_verified_vendor = serializers.BooleanField()
    is_active = serializers.BooleanField(source='user.is_active')

class AdminVendorApprovalSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()
    approve = serializers.BooleanField()

class AdminVendorSuspendSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()
    suspend = serializers.BooleanField()

class AdminVendorKYCSerializer(serializers.Serializer):
    user_uuid = serializers.UUIDField()

class AdminVendorActionResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    approved = serializers.BooleanField(required=False)
    suspended = serializers.BooleanField(required=False)
    message = serializers.CharField(required=False, allow_blank=True)



class AdminProfileResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = AdminUserManagementSerializer()


# =====================================================
# RESPONSE WRAPPER SERIALIZERS
# =====================================================
class SuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField(required=False, allow_blank=True)


class VendorOrdersSummaryResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Order counts: pending, paid, shipped, delivered, canceled"
    )


class VendorAnalyticsResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField(
        help_text="Analytics data with total_revenue and top_products"
    )


class AdminFinancePayoutResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Payout amount"
    )
    message = serializers.CharField(required=False, allow_blank=True)
