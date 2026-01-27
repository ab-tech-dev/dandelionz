from rest_framework import serializers
from .models import (
    Order, OrderItem, Payment, ShippingAddress, TransactionLog, Refund, 
    Wallet, WalletTransaction, InstallmentPlan, InstallmentPayment, OrderStatusHistory
)
from store.models import Product
from decimal import Decimal
from django.utils import timezone


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'description', 'tags', 'brand', 'variants', 'discount']
        read_only_fields = fields
        ref_name = "TransactionProductSerializer"


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )
    item_subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'product', 'product_id', 'quantity', 'price_at_purchase', 'item_subtotal']
        read_only_fields = ['id', 'product', 'item_subtotal', 'price_at_purchase']

    def get_item_subtotal(self, obj):
        return obj.item_subtotal

    def create(self, validated_data):
        product = validated_data.get('product')
        if not validated_data.get('price_at_purchase'):
            validated_data['price_at_purchase'] = product.price
        return super().create(validated_data)


class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = ['id', 'order', 'full_name', 'address', 'city', 'state', 'country', 'postal_code', 'phone_number']
        read_only_fields = ['id']


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.order_id', read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'order_id', 'reference', 'amount', 'status', 'gateway', 'paid_at', 'verified', 'created_at']
        read_only_fields = ['id', 'order_id', 'paid_at', 'verified', 'reference', 'created_at']


# ========================
# TIMELINE SERIALIZER
# ========================
class OrderTimelineEventSerializer(serializers.Serializer):
    """Serializer for individual timeline events in order tracking"""
    status = serializers.CharField()
    label = serializers.CharField()
    timestamp = serializers.DateTimeField(allow_null=True)
    completed = serializers.BooleanField()


def get_order_timeline(order):
    """
    Generate timeline array for an order showing all status transitions.
    Returns list of timeline events from initial PENDING to current status.
    """
    # Define the standard order timeline progression
    TIMELINE_TEMPLATE = [
        {
            'status': Order.Status.PENDING,
            'label': 'Order Placed',
            'timestamp_field': 'ordered_at',
        },
        {
            'status': Order.Status.PAID,
            'label': 'Payment Confirmed',
            'timestamp_field': 'payment.paid_at',  # From Payment model
        },
        {
            'status': Order.Status.SHIPPED,
            'label': 'Product Shipped',
            'timestamp_field': 'shipped_at',
        },
        {
            'status': Order.Status.DELIVERED,
            'label': 'Delivered',
            'timestamp_field': 'delivered_at',
        },
    ]
    
    # Handle RETURNED and CANCELED statuses
    if order.status == Order.Status.RETURNED:
        TIMELINE_TEMPLATE = [
            {
                'status': Order.Status.PENDING,
                'label': 'Order Placed',
                'timestamp_field': 'ordered_at',
            },
            {
                'status': Order.Status.PAID,
                'label': 'Payment Confirmed',
                'timestamp_field': 'payment.paid_at',
            },
            {
                'status': Order.Status.SHIPPED,
                'label': 'Product Shipped',
                'timestamp_field': 'shipped_at',
            },
            {
                'status': Order.Status.DELIVERED,
                'label': 'Delivered',
                'timestamp_field': 'delivered_at',
            },
            {
                'status': Order.Status.RETURNED,
                'label': 'Returned',
                'timestamp_field': 'returned_at',
            },
        ]
    elif order.status == Order.Status.CANCELED:
        # For canceled orders, show only up to where it was canceled
        TIMELINE_TEMPLATE = [
            {
                'status': Order.Status.PENDING,
                'label': 'Order Placed',
                'timestamp_field': 'ordered_at',
            },
            {
                'status': Order.Status.CANCELED,
                'label': 'Order Canceled',
                'timestamp_field': 'updated_at',  # Use updated_at as fallback for canceled
            },
        ]
    
    timeline = []
    
    for event in TIMELINE_TEMPLATE:
        status = event['status']
        label = event['label']
        timestamp_field = event['timestamp_field']
        
        # Get timestamp based on field path
        timestamp = None
        if timestamp_field == 'payment.paid_at':
            timestamp = order.payment.paid_at if hasattr(order, 'payment') and order.payment else None
        else:
            timestamp = getattr(order, timestamp_field, None)
        
        # Determine if this status is completed
        # A status is completed if the order has reached or passed this status
        completed = False
        if order.status == Order.Status.CANCELED:
            # For canceled orders
            completed = status == Order.Status.PENDING or status == Order.Status.CANCELED
        elif order.status == Order.Status.RETURNED:
            # For returned orders, all events up to RETURNED are completed
            completed = True
        else:
            # For normal progression
            STATUS_ORDER = [
                Order.Status.PENDING,
                Order.Status.PAID,
                Order.Status.SHIPPED,
                Order.Status.DELIVERED,
            ]
            if order.status in STATUS_ORDER:
                current_index = STATUS_ORDER.index(order.status)
                event_index = STATUS_ORDER.index(status) if status in STATUS_ORDER else -1
                completed = event_index <= current_index
        
        timeline.append({
            'status': status,
            'label': label,
            'timestamp': timestamp,
            'completed': completed,
        })
    
    return timeline


class RefundSerializer(serializers.ModelSerializer):
    payment_reference = serializers.CharField(source='payment.reference', read_only=True)
    order_id = serializers.CharField(source='payment.order.order_id', read_only=True)
    customer_email = serializers.EmailField(source='payment.order.customer.email', read_only=True)

    class Meta:
        model = Refund
        fields = [
            'id',
            'payment_reference',
            'order_id',
            'customer_email',
            'reason',
            'refunded_amount',
            'status',
            'created_at',
            'processed_at'
        ]
        read_only_fields = ['status', 'created_at', 'processed_at']


class TransactionLogSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(source='order.order_id', read_only=True, allow_null=True)

    class Meta:
        model = TransactionLog
        fields = ['id', 'order_id', 'message', 'level', 'created_at']
        read_only_fields = fields


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ['id', 'transaction_type', 'amount', 'source', 'created_at']
        read_only_fields = fields


class WalletSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    transactions = WalletTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Wallet
        fields = ['id', 'user_email', 'balance', 'updated_at', 'transactions']
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source='customer.email', read_only=True)
    order_items = OrderItemSerializer(many=True, read_only=True)
    shipping_address = ShippingAddressSerializer(read_only=True)
    payment = PaymentSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_with_delivery = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_paid = serializers.BooleanField(read_only=True)
    is_delivered = serializers.BooleanField(read_only=True)
    logs = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_email', 'status', 'payment_status',
            'total_price', 'delivery_fee', 'discount', 'subtotal', 'total_with_delivery',
            'tracking_number', 'ordered_at', 'shipped_at', 'delivered_at', 'returned_at', 
            'updated_at', 'is_paid', 'is_delivered',
            'order_items', 'shipping_address', 'payment', 'logs', 'timeline'
        ]
        read_only_fields = ['id', 'order_id', 'subtotal', 'total_with_delivery', 'is_paid', 'is_delivered', 'ordered_at', 'updated_at', 'order_items', 'payment', 'logs', 'shipped_at', 'delivered_at', 'returned_at', 'timeline']

    def get_logs(self, obj):
        request = self.context.get('request', None)
        if request and request.user and request.user.is_staff:
            qs = obj.logs.all().order_by('-created_at')
            return TransactionLogSerializer(qs, many=True).data
        return []

    def get_timeline(self, obj):
        """Generate and serialize the order timeline"""
        timeline_data = get_order_timeline(obj)
        return OrderTimelineEventSerializer(timeline_data, many=True).data


# ========================
# ORDER RECEIPT SERIALIZER
# ========================
class OrderReceiptSerializer(serializers.ModelSerializer):
    """
    Serializer for order receipts/invoices.
    Includes all granular financial details needed for receipt display.
    """
    customer_email = serializers.EmailField(source='customer.email', read_only=True)
    order_items = OrderItemSerializer(many=True, read_only=True)
    shipping_address = ShippingAddressSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_with_delivery = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_method = serializers.SerializerMethodField()
    transaction_reference = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer_email', 'status', 'payment_status',
            'ordered_at', 'shipped_at', 'delivered_at', 'tracking_number',
            # Financial details
            'subtotal',
            'total_with_delivery',
            'delivery_fee',
            'discount',
            'total_price',
            'payment_method',
            'transaction_reference',
            # Related data
            'order_items',
            'shipping_address',
        ]
        read_only_fields = fields

    def get_payment_method(self, obj):
        """Get payment method from associated Payment record"""
        if hasattr(obj, 'payment') and obj.payment:
            return obj.payment.gateway  # e.g., "Paystack", "Card", "Bank Transfer"
        return None

    def get_transaction_reference(self, obj):
        """Get transaction reference from associated Payment record"""
        if hasattr(obj, 'payment') and obj.payment:
            return obj.payment.reference
        return None


# ========================
# INSTALLMENT PAYMENT SERIALIZERS
# ========================
class InstallmentPaymentSerializer(serializers.ModelSerializer):
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = InstallmentPayment
        fields = [
            'id', 'payment_number', 'amount', 'status', 'due_date', 'payment_date',
            'reference', 'gateway', 'paid_at', 'verified', 'created_at', 'is_overdue'
        ]
        read_only_fields = ['id', 'reference', 'paid_at', 'verified', 'created_at', 'updated_at', 'is_overdue']

    def get_is_overdue(self, obj):
        return obj.is_overdue()


class InstallmentPlanSerializer(serializers.ModelSerializer):
    installments = InstallmentPaymentSerializer(many=True, read_only=True)
    order_id = serializers.UUIDField(source='order.order_id', read_only=True)
    paid_installments_count = serializers.SerializerMethodField()
    pending_installments_count = serializers.SerializerMethodField()
    is_fully_paid = serializers.SerializerMethodField()

    class Meta:
        model = InstallmentPlan
        fields = [
            'id', 'order_id', 'duration', 'total_amount', 'installment_amount',
            'number_of_installments', 'paid_installments_count', 'pending_installments_count',
            'status', 'is_fully_paid', 'start_date', 'created_at', 'updated_at', 'installments'
        ]
        read_only_fields = [
            'id', 'order_id', 'installment_amount', 'number_of_installments',
            'start_date', 'created_at', 'updated_at', 'installments',
            'paid_installments_count', 'pending_installments_count', 'is_fully_paid'
        ]

    def get_paid_installments_count(self, obj):
        return obj.get_paid_installments_count()

    def get_pending_installments_count(self, obj):
        return obj.get_pending_installments_count()

    def get_is_fully_paid(self, obj):
        return obj.is_fully_paid()

    def create(self, validated_data):
        """Create installment plan with related installment payments"""
        duration = validated_data.get('duration')
        total_amount = validated_data.get('total_amount')
        
        # Get number of installments from duration
        num_installments = InstallmentPlan.DURATION_INSTALLMENTS.get(duration, 1)
        installment_amount = total_amount / Decimal(num_installments)
        
        # Create the plan
        plan = InstallmentPlan.objects.create(
            number_of_installments=num_installments,
            installment_amount=installment_amount,
            **validated_data
        )
        
        # Create individual installment payments
        from django.utils import timezone
        from datetime import timedelta
        
        current_date = timezone.now()
        
        # Determine interval based on duration
        if duration == '1_month':
            interval = timedelta(days=30)
        elif duration == '3_months':
            interval = timedelta(days=30)
        elif duration == '6_months':
            interval = timedelta(days=30)
        elif duration == '1_year':
            interval = timedelta(days=30)
        else:
            interval = timedelta(days=30)
        
        for i in range(1, num_installments + 1):
            due_date = current_date + (interval * i)
            InstallmentPayment.objects.create(
                installment_plan=plan,
                payment_number=i,
                amount=installment_amount,
                due_date=due_date,
                reference=f"{plan.order.order_id}-installment-{i}"
            )
        
        return plan


class InstallmentCheckoutSerializer(serializers.Serializer):
    """Serializer for creating an order with installment plan"""
    duration = serializers.ChoiceField(choices=InstallmentPlan.DurationChoice.choices)
    
    def validate_duration(self, value):
        if value not in InstallmentPlan.DURATION_INSTALLMENTS:
            raise serializers.ValidationError("Invalid installment duration.")
        return value
