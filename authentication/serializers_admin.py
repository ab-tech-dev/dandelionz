"""
Admin-specific serializers for user management, order management, and admin profile operations.
These serializers enforce strict data validation and expose only necessary fields for admin operations.
"""

from decimal import Decimal

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
        try:
            if not obj or not hasattr(obj, 'suspensions'):
                return []
            suspensions = obj.suspensions.all()[:10]  # Last 10 suspensions
            return DashboardUserSuspensionSerializer(suspensions, many=True).data
        except Exception:
            return []


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


def _installment_plan_summary(obj):
    """Lean, read-only installment progress for admin order views. None when not on a plan."""
    plan = getattr(obj, 'installment_plan', None)
    if not plan:
        return None
    return {
        'id': plan.id,
        'status': plan.status,
        'total_amount': float(plan.total_amount),
        'amount_paid': float(plan.amount_paid),
        'balance_remaining': float(plan.balance_remaining),
        'paid_fraction': float(round(plan.paid_fraction, 4)),
    }


class AdminDashboardOrderListSerializer(serializers.ModelSerializer):
    """Lightweight order info for admin list views"""
    customer = serializers.SerializerMethodField()
    current_status = serializers.CharField(source='status', read_only=True)
    installment_plan = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'order_id', 'customer', 'current_status', 'total_price',
            'delivery_fee', 'payment_status', 'ordered_at', 'updated_at', 'status',
            'installment_plan',
        ]
        read_only_fields = fields

    def get_customer(self, obj):
        """Return customer object with necessary details"""
        if obj.customer:
            return {
                'full_name': obj.customer.full_name,
                'email': obj.customer.email,
                'phone_number': getattr(obj.customer, 'phone_number', '')
            }
        return None

    def get_installment_plan(self, obj):
        return _installment_plan_summary(obj)


class AdminDashboardOrderDetailSerializer(serializers.ModelSerializer):
    """Full order details for admin inspection"""
    customer = serializers.SerializerMethodField()
    order_items = AdminDashboardOrderItemSerializer(many=True, read_only=True)
    status_history = AdminDashboardOrderStatusHistorySerializer(many=True, read_only=True)
    current_status = serializers.CharField(source='status', read_only=True)
    installment_plan = serializers.SerializerMethodField()
    shipping_address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'order_id', 'customer', 'current_status',
            'total_price', 'delivery_fee', 'delivery_fee_paid', 'discount', 'payment_status',
            'expected_delivery_earliest', 'expected_delivery_latest',
            'tracking_number', 'ordered_at', 'updated_at', 'status',
            'order_items', 'status_history', 'installment_plan',
            'shipping_address', 'customer_lat', 'customer_lng',
        ]
        read_only_fields = fields

    def get_shipping_address(self, obj):
        """The customer's delivery destination - needed to know where to ship and to make
        sense of the calculated delivery fee. Was never exposed here; admins saw nothing."""
        address = getattr(obj, 'shipping_address', None)
        if not address:
            return None
        return {
            'full_name': address.full_name,
            'address': address.address,
            'city': address.city,
            'state': address.state,
            'country': address.country,
            'postal_code': address.postal_code,
            'phone_number': address.phone_number,
        }

    def get_installment_plan(self, obj):
        return _installment_plan_summary(obj)
    
    def get_customer(self, obj):
        """Return customer object with all necessary details"""
        if obj.customer:
            return {
                'full_name': obj.customer.full_name,
                'email': obj.customer.email,
                'phone_number': getattr(obj.customer, 'phone_number', ''),
                'uuid': str(obj.customer.uuid) if hasattr(obj.customer, 'uuid') else None
            }
        return None


class AdminDashboardOrderCancelSerializer(serializers.Serializer):
    """Serializer for cancelling orders"""
    reason = serializers.CharField(
        max_length=1000,
        required=True,
        help_text="Reason for order cancellation"
    )


class AdminDashboardOrderStatusUpdateSerializer(serializers.Serializer):
    """Serializer for updating order status (admin)"""
    status = serializers.CharField()

    def validate_status(self, value):
        """
        Accept frontend alias PROCESSING and map it to SHIPPED.
        Also allow case-insensitive status values.
        """
        status_value = str(value or "").strip().upper()
        alias_map = {
            "PROCESSING": Order.Status.SHIPPED,
        }
        normalized = alias_map.get(status_value, status_value)
        valid_statuses = {choice[0] for choice in Order.Status.choices}

        if normalized not in valid_statuses:
            raise serializers.ValidationError(
                f"Invalid status '{value}'. Valid values: {', '.join(sorted(valid_statuses | {'PROCESSING'}))}"
            )

        return normalized


class AdminSetDeliverySerializer(serializers.Serializer):
    """
    Admin sets the expected-delivery window (a RANGE) and the delivery fee in one action.

    Either pass use_default to apply the platform's default window, or provide both an
    earliest and a latest date. The fee may be zero (free delivery), which needs no second
    payment; a positive fee becomes due before the order can ship.
    """
    use_default = serializers.BooleanField(
        required=False, default=False,
        help_text="Apply the default delivery window instead of explicit dates.",
    )
    expected_delivery_earliest = serializers.DateTimeField(required=False, allow_null=True)
    expected_delivery_latest = serializers.DateTimeField(required=False, allow_null=True)
    delivery_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"),
        help_text="Delivery fee to charge the customer (0 for free delivery).",
    )

    def validate(self, data):
        if not data.get('use_default'):
            earliest = data.get('expected_delivery_earliest')
            latest = data.get('expected_delivery_latest')
            if earliest is None or latest is None:
                raise serializers.ValidationError(
                    "Provide both expected_delivery_earliest and expected_delivery_latest, "
                    "or set use_default to true."
                )
            if earliest > latest:
                raise serializers.ValidationError(
                    "expected_delivery_earliest must be on or before expected_delivery_latest."
                )
        return data


# =====================================================
# ADMIN PROFILE MANAGEMENT SERIALIZERS
# =====================================================

class AdminDashboardProfileSerializer(serializers.ModelSerializer):
    """Admin's own profile information"""
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['uuid', 'email', 'full_name', 'phone_number', 'profile_picture', 'created_at', 'updated_at']
        read_only_fields = ['uuid', 'email', 'created_at', 'updated_at']

    def get_profile_picture(self, obj):
        try:
            if hasattr(obj, 'profile_picture') and obj.profile_picture:
                return f"https://res.cloudinary.com/dhpny4uce/{obj.profile_picture}"
        except Exception:
            return None
        return None


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
