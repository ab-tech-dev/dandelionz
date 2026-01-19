"""
Admin-specific serializers for user management, order management, and admin profile operations.
These serializers enforce strict data validation and expose only necessary fields for admin operations.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from authentication.models import AdminAuditLog, UserSuspension
from transactions.models import Order, OrderStatusHistory, OrderItem

CustomUser = get_user_model()


# =====================================================
# USER MANAGEMENT SERIALIZERS
# =====================================================

class AdminDashboardUserListSerializer(serializers.ModelSerializer):
    """Lightweight user info for admin list views"""
    total_orders = serializers.IntegerField(read_only=True)
    total_spend = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta:
        model = CustomUser
        fields = ['uuid', 'email', 'full_name', 'phone_number', 'status', 'role', 'created_at', 'total_orders', 'total_spend']
        read_only_fields = ['uuid', 'created_at', 'total_orders', 'total_spend']


class AdminDashboardUserDetailSerializer(serializers.ModelSerializer):
    """Full user details for admin inspection"""
    total_orders = serializers.IntegerField(read_only=True)
    total_spend = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    suspension_history = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'uuid', 'email', 'full_name', 'phone_number', 'status', 'role',
            'is_verified', 'created_at', 'updated_at', 'total_orders', 'total_spend',
            'suspension_history'
        ]
        read_only_fields = ['uuid', 'created_at', 'updated_at', 'total_orders', 'total_spend']
    
    def get_suspension_history(self, obj):
        """Return suspension history for this user"""
        suspensions = obj.suspensions.all()[:10]  # Last 10 suspensions
        return DashboardUserSuspensionSerializer(suspensions, many=True).data


class DashboardUserSuspensionSerializer(serializers.ModelSerializer):
    admin_email = serializers.CharField(source='admin.email', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = UserSuspension
        fields = ['id', 'action', 'reason', 'user_email', 'admin_email', 'created_at']
        read_only_fields = ['id', 'created_at']


class AdminDashboardUserSuspendSerializer(serializers.Serializer):
    """Serializer for suspending/reinstating users"""
    reason = serializers.CharField(
        max_length=1000,
        required=True,
        help_text="Reason for suspension or reinstatement"
    )
    action = serializers.ChoiceField(
        choices=['suspend', 'reinstate'],
        default='suspend',
        required=False
    )


# =====================================================
# ORDER MANAGEMENT SERIALIZERS
# =====================================================

class AdminDashboardOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    vendor_name = serializers.CharField(source='product.store.store_name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'quantity', 'price_at_purchase', 'item_subtotal', 'vendor_name']
        read_only_fields = ['id', 'item_subtotal']


class AdminDashboardOrderStatusHistorySerializer(serializers.ModelSerializer):
    admin_email = serializers.CharField(source='admin.email', read_only=True, allow_null=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'status', 'changed_by', 'admin_email', 'reason', 'changed_at']
        read_only_fields = ['id', 'changed_at']


class AdminDashboardOrderListSerializer(serializers.ModelSerializer):
    """Lightweight order info for admin list views"""
    customer_email = serializers.CharField(source='customer.email', read_only=True)
    current_status = serializers.CharField(source='status', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'order_id', 'customer_email', 'current_status', 'total_price',
            'delivery_fee', 'payment_status', 'ordered_at', 'updated_at'
        ]
        read_only_fields = fields


class AdminDashboardOrderDetailSerializer(serializers.ModelSerializer):
    """Full order details for admin inspection"""
    customer_email = serializers.CharField(source='customer.email', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone_number', read_only=True)
    order_items = AdminDashboardOrderItemSerializer(many=True, read_only=True)
    status_history = AdminDashboardOrderStatusHistorySerializer(many=True, read_only=True)
    current_status = serializers.CharField(source='status', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'order_id', 'customer_email', 'customer_phone', 'current_status',
            'total_price', 'delivery_fee', 'discount', 'payment_status',
            'tracking_number', 'ordered_at', 'updated_at', 'order_items',
            'status_history'
        ]
        read_only_fields = fields


class AdminDashboardOrderCancelSerializer(serializers.Serializer):
    """Serializer for cancelling orders"""
    reason = serializers.CharField(
        max_length=1000,
        required=True,
        help_text="Reason for order cancellation"
    )


# =====================================================
# ADMIN PROFILE MANAGEMENT SERIALIZERS
# =====================================================

class AdminDashboardProfileSerializer(serializers.ModelSerializer):
    """Admin's own profile information"""
    class Meta:
        model = CustomUser
        fields = ['uuid', 'email', 'full_name', 'phone_number', 'profile_picture', 'created_at', 'updated_at']
        read_only_fields = ['uuid', 'email', 'created_at', 'updated_at']


class AdminDashboardProfileUpdateSerializer(serializers.ModelSerializer):
    """Update admin profile (name, phone, email)"""
    class Meta:
        model = CustomUser
        fields = ['full_name', 'phone_number']


class AdminDashboardPasswordVerifySerializer(serializers.Serializer):
    """Verify current password before allowing sensitive operations"""
    current_password = serializers.CharField(write_only=True, required=True)


class AdminDashboardPasswordChangeSerializer(serializers.Serializer):
    """Change admin password with verification"""
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, required=True, min_length=8)
    
    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError("Passwords do not match")
        return data


class AdminDashboardPhotoUploadSerializer(serializers.ModelSerializer):
    """Upload profile photo"""
    class Meta:
        model = CustomUser
        fields = ['profile_picture']


# =====================================================
# AUDIT LOG SERIALIZERS
# =====================================================

class AdminDashboardAuditLogSerializer(serializers.ModelSerializer):
    """View admin audit logs"""
    admin_email = serializers.CharField(source='admin.email', read_only=True, allow_null=True)
    
    class Meta:
        model = AdminAuditLog
        fields = ['id', 'admin_email', 'action', 'target_entity', 'target_id', 'reason', 'details', 'created_at']
        read_only_fields = fields
