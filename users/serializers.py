from rest_framework import serializers
from django.contrib.auth import get_user_model
import base64
import uuid
import io
import cloudinary.uploader
import logging

from .models import (
    Vendor,
    Customer,
    BusinessAdmin,
    DeliveryAgent
)
from .notification_models import Notification

User = get_user_model()
logger = logging.getLogger(__name__)


# =====================================================
# CUSTOM FIELDS FOR BASE64 IMAGE UPLOAD
# =====================================================
class Base64ImageField(serializers.Field):
    """
    A custom serializer field for handling base64 encoded image uploads.
    Converts base64 to Cloudinary and stores the public_id.
    """
    def to_representation(self, value):
        """Return the Cloudinary public_id as-is (UserBaseSerializer will format it as URL)"""
        if value:
            return str(value)
        return None

    def to_internal_value(self, data):
        """
        Convert base64 encoded image to Cloudinary and return public_id
        Expects data in format: 'data:image/jpeg;base64,<base64_string>'
        or just the base64 string
        """
        if not data:
            return None

        # Check if it's already a Cloudinary reference or URL
        if isinstance(data, str):
            if data.startswith('http'):
                # It's already a URL, can't process
                return None
            if data.startswith('data:') is False and len(data) > 50:
                # Looks like it might be a public_id already, return as-is
                return data

        try:
            base64_str = None
            ext = 'jpg'
            
            # Handle data URL format
            if isinstance(data, str) and data.startswith('data:'):
                # Extract base64 string from data URL
                parts = data.split(',', 1)
                if len(parts) != 2:
                    raise ValueError("Invalid data URL format")
                
                header, base64_str = parts
                # Extract file extension from header (e.g., 'data:image/jpeg;base64,')
                if 'image/' in header:
                    ext_match = header.split('/')
                    if len(ext_match) > 1:
                        ext = ext_match[1].split(';')[0]
                else:
                    ext = 'jpg'
            elif isinstance(data, str):
                # Assume it's just base64 string
                base64_str = data
                ext = 'jpg'
            else:
                raise ValueError("Image data must be a base64 string")

            if not base64_str:
                raise ValueError("No base64 data found")

            # Decode base64
            try:
                image_data = base64.b64decode(base64_str, validate=True)
            except Exception as e:
                raise ValueError(f"Invalid base64 encoding: {str(e)}")
            
            if len(image_data) == 0:
                raise ValueError("Image data is empty")
            
            # Create a BytesIO object for Cloudinary
            image_file = io.BytesIO(image_data)
            image_file.name = f"profile_{uuid.uuid4().hex[:12]}.{ext}"
            
            logger.info(f"Uploading image to Cloudinary: {image_file.name}, size: {len(image_data)} bytes")
            
            # Upload to Cloudinary
            response = cloudinary.uploader.upload(
                image_file,
                resource_type='auto',
                folder='dandelionz/profiles',
                public_id=f"profile_{uuid.uuid4().hex[:12]}",
                overwrite=False,
                timeout=60
            )
            
            # Check for upload errors
            if 'error' in response:
                error_msg = response['error'].get('message', 'Unknown upload error') if isinstance(response['error'], dict) else str(response['error'])
                logger.error(f"Cloudinary upload error: {error_msg}")
                raise ValueError(f"Cloudinary upload failed: {error_msg}")
            
            # Return the public_id that CloudinaryField will store
            public_id = response.get('public_id')
            if not public_id:
                raise ValueError("No public_id returned from Cloudinary")
            
            logger.info(f"Successfully uploaded image to Cloudinary: {public_id}")
            return public_id
        
        except ValueError as ve:
            logger.error(f"Validation error uploading base64 image: {str(ve)}")
            raise serializers.ValidationError(str(ve))
        except Exception as e:
            logger.error(f"Unexpected error uploading base64 image: {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"Failed to process image: {str(e)}")


# =====================================================
# BASE USER SERIALIZER (READ-ONLY USER DATA)
# =====================================================
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
        try:
            if hasattr(obj, 'profile_picture') and obj.profile_picture:
                # Prepend your Cloudinary base URL
                return f"https://res.cloudinary.com/dhpny4uce/{obj.profile_picture}"
        except Exception:
            pass
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
    profile_picture = Base64ImageField(source='user.profile_picture', required=False, allow_null=True)

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
    user_email = serializers.EmailField(
        source='user.email',
        read_only=True,
        allow_null=True
    )
    user_name = serializers.CharField(
        source='user.full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            'id',
            'user',
            'user_email',
            'user_name',
            'title',
            'message',
            'priority',
            'category',
            'is_read',
            'is_archived',
            'is_draft',
            'scheduled_for',
            'sent_at',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'user_email',
            'user_name',
            'created_at',
        ]


class AdminNotificationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating admin broadcast notifications.
    Handles creating notifications with metadata for specific recipient groups.
    """
    
    user_uuid = serializers.UUIDField(write_only=True, required=False)
    recipient_group = serializers.ChoiceField(
        choices=['admin', 'vendor', 'customer', 'all'],
        write_only=True,
        required=False
    )
    is_draft = serializers.BooleanField(required=False, default=False)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    send_websocket = serializers.BooleanField(required=False, default=True)
    send_email = serializers.BooleanField(required=False, default=False)
    send_push = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Notification
        fields = [
            'id',
            'user',
            'user_uuid',
            'recipient_group',
            'notification_type',
            'title',
            'message',
            'description',
            'priority',
            'category',
            'action_url',
            'action_text',
            'metadata',
            'expires_at',
            'is_draft',
            'scheduled_for',
            'send_websocket',
            'send_email',
            'send_push',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_priority(self, value):
        """Validate that priority is one of the allowed choices"""
        valid_priorities = ['low', 'normal', 'high', 'urgent']
        if value not in valid_priorities:
            raise serializers.ValidationError(
                f"priority must be one of {valid_priorities}"
            )
        return value

    def validate(self, data):
        """
        Cross-field validation:
        - expires_at must be in the future if provided
        - scheduled_for must be in the future if provided
        """
        from django.utils import timezone
        
        expires_at = data.get('expires_at')
        if expires_at and expires_at <= timezone.now():
            raise serializers.ValidationError(
                "expires_at must be a future date and time"
            )

        scheduled_for = data.get('scheduled_for')
        if scheduled_for and scheduled_for <= timezone.now():
            raise serializers.ValidationError(
                "scheduled_for must be a future date and time"
            )
        
        return data


class AdminNotificationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing admin broadcast notifications with full details.
    """
    notification_type_display = serializers.CharField(
        source='notification_type.display_name',
        read_only=True,
        allow_null=True
    )
    user_email = serializers.CharField(
        source='user.email',
        read_only=True,
        allow_null=True
    )
    user_name = serializers.CharField(
        source='user.full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'message',
            'priority',
            'category',
            'notification_type_display',
            'user',
            'user_email',
            'user_name',
            'is_read',
            'is_archived',
            'is_draft',
            'scheduled_for',
            'sent_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'user_email',
            'user_name',
            'notification_type_display',
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


# =====================================================
# VENDOR ORDER SERIALIZERS
# =====================================================
class VendorOrderCustomerSerializer(serializers.Serializer):
    """Serializer for customer information in order responses"""
    full_name = serializers.CharField()
    email = serializers.EmailField()
    phone_number = serializers.CharField(required=False, allow_blank=True)


class VendorOrderItemSerializer(serializers.Serializer):
    """Serializer for order items in vendor order responses"""
    product_name = serializers.CharField(source='product.name')
    quantity = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, source='price_at_purchase')


class VendorOrderListItemSerializer(serializers.Serializer):
    """Serializer for order items in the order list (paginated results)"""
    uuid = serializers.UUIDField(source='order_id')
    order_id = serializers.CharField()
    customer = VendorOrderCustomerSerializer(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, source='total_price')
    status = serializers.CharField()
    created_at = serializers.DateTimeField(source='ordered_at')


class VendorOrderDetailSerializer(serializers.Serializer):
    """Serializer for detailed order information"""
    uuid = serializers.UUIDField(source='order_id')
    order_id = serializers.CharField()
    customer = VendorOrderCustomerSerializer(read_only=True)
    items = VendorOrderItemSerializer(source='order_items', many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, source='total_price')
    status = serializers.CharField()
    shipping_address = serializers.CharField()
    created_at = serializers.DateTimeField(source='ordered_at')
    updated_at = serializers.DateTimeField()


class VendorOrderSummarySerializer(serializers.Serializer):
    """Serializer for order summary with status counts"""
    pending = serializers.IntegerField()
    paid = serializers.IntegerField()
    shipped = serializers.IntegerField()
    delivered = serializers.IntegerField()
    canceled = serializers.IntegerField()


from rest_framework import serializers
from store.models import Product


class AdminProductUpdateSerializer(serializers.Serializer):
    product_slug = serializers.SlugField(help_text="Product slug for identification")
    name = serializers.CharField(required=False, help_text="Product name")
    description = serializers.CharField(required=False, help_text="Product description")
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, help_text="Product price")
    discount = serializers.IntegerField(required=False, help_text="Discount percentage (0-100)")
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
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_orders = serializers.IntegerField()
    pending_orders = serializers.IntegerField()
    total_vendors = serializers.IntegerField()


class SalesChartDataSerializer(serializers.Serializer):
    """Serializer for individual sales chart data points"""
    period = serializers.CharField()
    sales = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrderStatsSerializer(serializers.Serializer):
    """Serializer for order status breakdown"""
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    returned = serializers.IntegerField()


class AdminDetailedAnalyticsSerializer(serializers.Serializer):
    """Serializer for detailed admin analytics page data"""
    total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_vendors = serializers.IntegerField()
    total_orders = serializers.IntegerField()
    total_users = serializers.IntegerField()
    sales_chart_data = SalesChartDataSerializer(many=True)
    order_stats = OrderStatsSerializer()



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
    """
    Serializer for admin to view all marketplace products with complete information.
    Includes all product details, pricing, inventory, and approval status.
    """
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    description = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.IntegerField()
    stock = serializers.IntegerField()
    brand = serializers.CharField()
    tags = serializers.CharField()
    variants = serializers.JSONField(allow_null=True)
    store = serializers.CharField(source='store.store_name')
    store_id = serializers.IntegerField(source='store.id')
    category = serializers.CharField(source='category.name', allow_null=True)
    approval_status = serializers.CharField()
    publish_status = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

class AdminProductDetailSerializer(serializers.Serializer):
    """
    Serializer for admin to view detailed product information including all attributes,
    pricing, discounts, inventory, vendor details, and approval information.
    """
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    description = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.IntegerField()
    stock = serializers.IntegerField()
    brand = serializers.CharField()
    tags = serializers.CharField()
    variants = serializers.JSONField(allow_null=True)
    store = serializers.CharField(source='store.store_name')
    store_id = serializers.IntegerField(source='store.id')
    store_email = serializers.CharField(source='store.user.email')
    category = serializers.CharField(source='category.name', allow_null=True)
    approval_status = serializers.CharField()
    publish_status = serializers.CharField()
    approved_by = serializers.CharField(source='approved_by.email', allow_null=True)
    approval_date = serializers.DateTimeField(allow_null=True)
    rejection_reason = serializers.CharField(allow_null=True)
    in_stock = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_in_stock(self, obj):
        """Check if product is in stock"""
        return obj.stock > 0 if obj.stock else False

    def get_final_price(self, obj):
        """Calculate final price after discount"""
        if not obj.price:
            return None
        from decimal import Decimal
        discount_amount = (obj.price * obj.discount) / Decimal('100')
        return obj.price - discount_amount


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
        try:
            if not obj or not hasattr(obj, 'assigned_orders'):
                return 0
            return obj.assigned_orders.count()
        except Exception:
            return 0
    
    def get_total_delivered(self, obj):
        try:
            if not obj or not hasattr(obj, 'assigned_orders'):
                return 0
            return obj.assigned_orders.filter(status='DELIVERED').count()
        except Exception:
            return 0

# =====================================================
# VENDOR WALLET & PAYMENT SERIALIZERS
# =====================================================

class WalletBalanceSerializer(serializers.Serializer):
    """Serializer for wallet balance response with available vs pending breakdown"""
    withdrawable_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    pending_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    pending_order_count = serializers.IntegerField(read_only=True)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_credits = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_debits = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_withdrawals = serializers.IntegerField(read_only=True)
    this_month_earnings = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class WalletTransactionListSerializer(serializers.Serializer):
    """Serializer for individual wallet transactions in list"""
    id = serializers.CharField(read_only=True)
    type = serializers.CharField(source='transaction_type', read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    description = serializers.CharField(source='source', read_only=True)
    status = serializers.SerializerMethodField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    
    def get_status(self, obj):
        # All wallet transactions are recorded as successful
        return 'successful'


class WithdrawalRequestSerializer(serializers.Serializer):
    """Serializer for withdrawal requests"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    pin = serializers.CharField(write_only=True, min_length=4, max_length=4)
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    account_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    
    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return value
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class WithdrawalResponseSerializer(serializers.Serializer):
    """Response serializer for withdrawal requests"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    reference = serializers.CharField(required=False)


class PaymentSettingsSerializer(serializers.Serializer):
    """Serializer for payment settings"""
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    account_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_name = serializers.CharField(max_length=200, read_only=True)
    recipient_code = serializers.CharField(max_length=100, read_only=True)
    has_pin = serializers.SerializerMethodField(read_only=True)
    
    def get_has_pin(self, obj):
        try:
            if hasattr(obj, "payment_pin"):
                return obj.payment_pin is not None
            user = getattr(obj, "user", None)
            if user and hasattr(user, "payment_pin"):
                return user.payment_pin is not None
        except Exception:
            pass
        return False


class PaymentSettingsUpdateSerializer(serializers.Serializer):
    """Serializer for updating payment settings"""
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    account_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_name = serializers.CharField(max_length=200, required=False, allow_blank=True)


class PaymentPINSerializer(serializers.Serializer):
    """Serializer for setting/changing payment PIN"""
    pin = serializers.CharField(write_only=True, min_length=4, max_length=4)
    confirm_pin = serializers.CharField(write_only=True, min_length=4, max_length=4)
    
    def validate(self, data):
        if data['pin'] != data['confirm_pin']:
            raise serializers.ValidationError("PINs do not match.")
        if not data['pin'].isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return data


class PINResetRequestSerializer(serializers.Serializer):
    """Serializer for PIN reset requests"""
    email = serializers.EmailField(read_only=True)


class PayoutRequestSerializer(serializers.Serializer):
    """Serializer for payout requests"""
    id = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    bank_name = serializers.CharField(read_only=True)
    account_number = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    processed_at = serializers.DateTimeField(read_only=True)


# =====================================================
# ADMIN WALLET & PAYMENT SERIALIZERS
# =====================================================
class AdminWalletBalanceSerializer(serializers.Serializer):
    """Serializer for admin wallet balance information"""
    withdrawable_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_withdrawals = serializers.IntegerField()
    this_month_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)


class AdminWalletTransactionSerializer(serializers.Serializer):
    """Serializer for admin wallet transactions"""
    id = serializers.CharField()
    type = serializers.CharField()  # DEBIT or CREDIT
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    description = serializers.CharField()
    status = serializers.CharField()  # SUCCESSFUL, FAILED, etc.
    created_at = serializers.DateTimeField()


class AdminPaymentSettingsSerializer(serializers.Serializer):
    """Serializer for admin payment settings (bank details)"""
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    account_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_name = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AdminWithdrawalSerializer(serializers.Serializer):
    """Serializer for admin withdrawal requests"""
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    pin = serializers.CharField(write_only=True, min_length=4, max_length=4)
    
    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return value


class AdminPaymentPINSerializer(serializers.Serializer):
    """Serializer for admin payment PIN management"""
    current_pin = serializers.CharField(write_only=True, min_length=4, max_length=4, required=False, allow_blank=True)
    new_pin = serializers.CharField(write_only=True, min_length=4, max_length=4)
    confirm_pin = serializers.CharField(write_only=True, min_length=4, max_length=4)
    
    def validate(self, data):
        if data['new_pin'] != data['confirm_pin']:
            raise serializers.ValidationError("PINs do not match.")
        if not data['new_pin'].isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return data


# =====================================================
# SETTLEMENT & DISPUTE SERIALIZERS
# =====================================================
class SettlementSummarySerializer(serializers.Serializer):
    """Serializer for settlement summary statistics"""
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payouts = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_settlements = serializers.DecimalField(max_digits=12, decimal_places=2)
    upcoming_payouts = serializers.IntegerField()


class VendorSettlementSerializer(serializers.Serializer):
    """Serializer for individual vendor settlements"""
    id = serializers.CharField()
    vendor_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payout_date = serializers.DateTimeField()
    status = serializers.CharField()  # PENDING, PROCESSED, FAILED


class DisputeSerializer(serializers.Serializer):
    """Serializer for customer disputes/refunds"""
    id = serializers.CharField()
    order_id = serializers.CharField()
    customer_name = serializers.CharField()
    vendor_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField()
    status = serializers.CharField()  # PENDING, APPROVED, REJECTED
    created_at = serializers.DateTimeField()


class DisputeResolutionSerializer(serializers.Serializer):
    """Serializer for resolving disputes"""
    action = serializers.CharField(required=True)  # APPROVE or REJECT
    admin_note = serializers.CharField(required=False, allow_blank=True)
    
    def validate_action(self, value):
        if value not in ['APPROVE', 'REJECT']:
            raise serializers.ValidationError("Action must be 'APPROVE' or 'REJECT'.")
        return value


# =====================================================
# ACCOUNT CLOSURE SERIALIZERS
# =====================================================
class CloseAccountSerializer(serializers.Serializer):
    """Serializer for account closure with password verification"""
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Current password for account closure confirmation"
    )


class AccountClosureResponseSerializer(serializers.Serializer):
    """Response serializer for successful account closure"""
    success = serializers.BooleanField()
    message = serializers.CharField()


class AccountClosureErrorSerializer(serializers.Serializer):
    """Response serializer for account closure errors"""
    success = serializers.BooleanField()
    error = serializers.CharField()
