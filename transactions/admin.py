from django.contrib import admin
from .models import Order, OrderItem, Payment, ShippingAddress, TransactionLog, Refund

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id','customer','status','total_price','payment_status','ordered_at')
    search_fields = ('order_id', 'customer__email', 'customer__username')
    list_filter = ('status','payment_status')

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id','order','product','quantity','price_at_purchase')
    search_fields = ('product__name',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference','order','amount','status','verified','paid_at')
    search_fields = ('reference','order__order_id')

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('order','level','created_at','message')
    list_filter = ('level',)

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('payment','status','refunded_amount','created_at')
