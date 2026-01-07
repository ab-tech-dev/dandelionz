from django.urls import path
from .views import (
    OrderListCreateView, OrderDetailView,
    OrderItemListCreateView, OrderItemDetailView,
    TransactionLogListView,
    CheckoutView, SecureVerifyPaymentView, PaystackWebhookView,
    RefundListView, RefundDetailView,
    CustomerWalletView, WalletTransactionListView, AdminWalletListView,
    InstallmentCheckoutView, InstallmentPlanListView, InstallmentPlanDetailView,
    InstallmentPaymentListView, VerifyInstallmentPaymentView, InstallmentWebhookView
)

urlpatterns = [
    # Order endpoints
    path('orders/', OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<uuid:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/<uuid:order_id>/items/', OrderItemListCreateView.as_view(), name='order-item-list-create'),
    path('order-items/<int:pk>/', OrderItemDetailView.as_view(), name='order-item-detail'),
    path('logs/', TransactionLogListView.as_view(), name='transaction-log-list'),

    # Checkout endpoints
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('checkout/installment/', InstallmentCheckoutView.as_view(), name='installment-checkout'),

    # Payment verification endpoint
    path('verify-payment/', SecureVerifyPaymentView.as_view(), name='verify-payment'),
    path('webhook/', PaystackWebhookView.as_view(), name='paystack-webhook'),

    # Installment plan endpoints
    path('installment-plans/', InstallmentPlanListView.as_view(), name='installment-plan-list'),
    path('installment-plans/<int:id>/', InstallmentPlanDetailView.as_view(), name='installment-plan-detail'),
    path('installment-plans/<int:plan_id>/payments/', InstallmentPaymentListView.as_view(), name='installment-payment-list'),
    path('verify-installment-payment/', VerifyInstallmentPaymentView.as_view(), name='verify-installment-payment'),
    path('installment-webhook/', InstallmentWebhookView.as_view(), name='installment-webhook'),

    # Refund endpoints
    path('refunds/', RefundListView.as_view(), name='refund-list'),
    path('refunds/<int:id>/', RefundDetailView.as_view(), name='refund-detail'),

    # Wallet endpoints
    path('wallet/', CustomerWalletView.as_view(), name='customer-wallet'),
    path('wallet/transactions/', WalletTransactionListView.as_view(), name='wallet-transactions'),
    path('admin/wallets/', AdminWalletListView.as_view(), name='admin-wallet-list'),
]
