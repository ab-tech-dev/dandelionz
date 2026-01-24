from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import (
    Vendor,
    Customer,
    BusinessAdmin,
    Notification,
    DeliveryAgent
)

User = get_user_model()


# =====================================================
# BASE USER SERIALIZER (READ-ONLY USER DATA)
# =====================================================
from rest_framework import serializers

class UserBaseSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()

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
        ref_name = "UsersProfileUserBase"

    def get_profile_picture(self, obj):
        if obj.profile_picture:
            # Prepend your Cloudinary base URL
            return f"https://res.cloudinary.com/dhpny4uce/{obj.profile_picture}"
        return None


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
    full_name = serializers.CharField(source='user.full_name', required=False, max_length=150)
    phone_number = serializers.CharField(source='user.phone_number', required=False, max_length=15, allow_blank=True)
    profile_picture = serializers.CharField(source='user.profile_picture', required=False, allow_blank=True)

    class Meta:
        model = Customer
        fields = [
            'shipping_address',
            'city',
            'country',
            'postal_code',
            'full_name',
            'phone_number',
            'profile_picture',
        ]

    def update(self, instance, validated_data):
        # Extract user data
        user_data = validated_data.pop('user', {})
        
        # Update user fields if provided
        user = instance.user
        if user_data:
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()
        
        # Update customer fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        return instance

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
            'recipient_code',
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


class AdminNotificationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating admin broadcast notifications.
    Handles sending, drafting, or scheduling notifications to specific recipient groups.
    """
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'message',
            'recipient_type',
            'status',
            'scheduled_at',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_recipient_type(self, value):
        """Validate that recipient_type is one of the allowed choices"""
        valid_types = ['USERS', 'VENDORS', 'ALL']
        if value not in valid_types:
            raise serializers.ValidationError(
                f"recipient_type must be one of {valid_types}"
            )
        return value

    def validate_status(self, value):
        """Validate that status is one of the allowed choices"""
        valid_statuses = ['Sent', 'Draft', 'Scheduled']
        if value not in valid_statuses:
            raise serializers.ValidationError(
                f"status must be one of {valid_statuses}"
            )
        return value

    def validate(self, data):
        """
        Cross-field validation:
        - If status is 'Scheduled', scheduled_at must be provided
        - scheduled_at must be in the future
        """
        status = data.get('status')
        scheduled_at = data.get('scheduled_at')
        
        if status == 'Scheduled':
            if not scheduled_at:
                raise serializers.ValidationError(
                    "scheduled_at is required when status is 'Scheduled'"
                )
            
            from django.utils import timezone
            if scheduled_at <= timezone.now():
                raise serializers.ValidationError(
                    "scheduled_at must be a future date and time"
                )
        
        return data

    def create(self, validated_data):
        """
        Create the notification and set created_by to the current user (admin).
        """
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)


class AdminNotificationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing admin broadcast notifications with full details.
    """
    created_by_email = serializers.EmailField(
        source='created_by.email',
        read_only=True,
        allow_null=True
    )
    created_by_name = serializers.CharField(
        source='created_by.full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'message',
            'recipient_type',
            'status',
            'scheduled_at',
            'created_by',
            'created_by_email',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_by',
            'created_by_email',
            'created_by_name',
            'created_at',
            'updated_at',
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
    product_slug = serializers.SlugField(help_text="Product slug for identification")
    name = serializers.CharField(required=False, help_text="Product name")
    description = serializers.CharField(required=False, help_text="Product description")
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, help_text="Product price")
    discounted_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, help_text="Discounted price if applicable")
    stock = serializers.IntegerField(required=False, help_text="Stock quantity")
    is_active = serializers.BooleanField(required=False, help_text="Whether product is active")

    def validate_product_slug(self, value):
        if not Product.objects.filter(slug=value).exists():
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
    total_users = serializers.IntegerField()
    total_vendors = serializers.IntegerField()
    total_orders = serializers.IntegerField()
    total_products = serializers.IntegerField()



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

class AdminVendorDetailSerializer(serializers.Serializer):
    """Detailed vendor information for admin dashboard"""
    user_uuid = serializers.UUIDField(source='user.uuid')
    email = serializers.EmailField(source='user.email')
    full_name = serializers.CharField(source='user.full_name')
    phone_number = serializers.CharField(source='user.phone_number')
    store_name = serializers.CharField()
    store_description = serializers.CharField()
    business_registration_number = serializers.CharField()
    address = serializers.CharField()
    bank_name = serializers.CharField()
    account_number = serializers.CharField()
    recipient_code = serializers.CharField()
    is_verified_vendor = serializers.BooleanField()
    is_active = serializers.BooleanField(source='user.is_active')
    is_verified = serializers.BooleanField(source='user.is_verified')
    created_at = serializers.DateTimeField(source='user.date_joined', read_only=True)

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


# =====================================================
# DELIVERY AGENT SERIALIZERS
# =====================================================
class DeliveryAgentProfileSerializer(serializers.ModelSerializer):
    """Serializer for delivery agent profile information"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    
    class Meta:
        model = DeliveryAgent
        fields = ['id', 'user_email', 'user_full_name', 'user_phone', 'phone', 'is_active', 'created_at']
        read_only_fields = ['id', 'user_email', 'user_full_name', 'user_phone', 'created_at']


class DeliveryAgentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating delivery agent profile"""
    class Meta:
        model = DeliveryAgent
        fields = ['phone', 'is_active']


class DeliveryAgentAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning orders to delivery agents"""
    order_id = serializers.CharField()
    delivery_agent_id = serializers.IntegerField()
    
    def validate_delivery_agent_id(self, value):
        try:
            DeliveryAgent.objects.get(id=value)
        except DeliveryAgent.DoesNotExist:
            raise serializers.ValidationError("Delivery agent not found")
        return value


class DeliveryAgentStatsSerializer(serializers.Serializer):
    """Serializer for delivery agent statistics"""
    total_assigned = serializers.IntegerField()
    total_delivered = serializers.IntegerField()
    pending_deliveries = serializers.IntegerField()
    delivery_success_rate = serializers.FloatField()


class DeliveryAgentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating delivery agents (admin only)"""
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = DeliveryAgent
        fields = ['email', 'full_name', 'phone', 'password', 'is_active']
    
    def create(self, validated_data):
        from authentication.models import CustomUser
        
        email = validated_data.pop('email')
        full_name = validated_data.pop('full_name')
        password = validated_data.pop('password')
        phone = validated_data.pop('phone')
        
        # Create user with DELIVERY_AGENT role
        user = CustomUser.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            phone_number=phone,
            role=CustomUser.Role.DELIVERY_AGENT,
            is_verified=True,  # Admin creates verified delivery agents
        )
        
        # Create delivery agent profile
        delivery_agent = DeliveryAgent.objects.create(
            user=user,
            phone=phone,
            is_active=validated_data.get('is_active', True)
        )
        
        return delivery_agent


class DeliveryAgentListSerializer(serializers.ModelSerializer):
    """Serializer for listing delivery agents (admin view)"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_full_name = serializers.CharField(source='user.full_name', read_only=True)
    total_assigned = serializers.SerializerMethodField()
    total_delivered = serializers.SerializerMethodField()
    
    class Meta:
        model = DeliveryAgent
        fields = ['id', 'user_email', 'user_full_name', 'phone', 'is_active', 'total_assigned', 'total_delivered', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_total_assigned(self, obj):
        return obj.assigned_orders.count()
    
    def get_total_delivered(self, obj):
        return obj.assigned_orders.filter(status='DELIVERED').count()
