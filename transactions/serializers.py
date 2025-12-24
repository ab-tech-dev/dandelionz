from rest_framework import serializers
from .models import Order, OrderItem, Payment, ShippingAddress, TransactionLog, Refund, Wallet, WalletTransaction
from store.models import Product
from decimal import Decimal


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'description']
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

    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'customer_email', 'status', 'payment_status',
            'total_price', 'delivery_fee', 'discount', 'subtotal', 'total_with_delivery',
            'ordered_at', 'updated_at', 'is_paid', 'is_delivered',
            'order_items', 'shipping_address', 'payment', 'logs'
        ]
        read_only_fields = ['id', 'order_id', 'subtotal', 'total_with_delivery', 'is_paid', 'is_delivered', 'ordered_at', 'updated_at', 'order_items', 'payment', 'logs']

    def get_logs(self, obj):
        request = self.context.get('request', None)
        if request and request.user and request.user.is_staff:
            qs = obj.logs.all().order_by('-created_at')
            return TransactionLogSerializer(qs, many=True).data
        return []
