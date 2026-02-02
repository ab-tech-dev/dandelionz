from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils import timezone
from django.db import transaction

from store.serializers import ProductSerializer, CreateProductSerializer

from users.serializers import (
    CustomerProfileSerializer,
    CustomerProfileUpdateSerializer,
    ChangePasswordSerializer,
    AdminAnalyticsSerializer,
    AdminDetailedAnalyticsSerializer,
    AdminFinancePayoutSerializer,
    AdminFinancePaymentSerializer,
    AdminOrderActionSerializer,
    AdminOrderActionResponseSerializer,
    AdminOrdersSummarySerializer,
    AdminProductActionResponseSerializer,
    AdminProductUpdateRequestSerializer,
    AdminProductListSerializer,
    AdminProductDetailSerializer,
    AdminVendorListSerializer,
    AdminVendorDetailSerializer,
    AdminVendorApprovalSerializer,
    AdminVendorActionResponseSerializer,
    AdminVendorSuspendSerializer,
    AdminVendorKYCSerializer,
    AdminProfileResponseSerializer,
    NotificationSerializer,
    AdminNotificationCreateSerializer,
    AdminNotificationListSerializer,
    VendorProfileSerializer,
    VendorOrdersSummaryResponseSerializer,
    VendorAnalyticsResponseSerializer,
    AdminFinancePayoutResponseSerializer,
    SuccessResponseSerializer,
    DeliveryAgentProfileSerializer,
    DeliveryAgentUpdateSerializer,
    DeliveryAgentAssignmentSerializer,
    DeliveryAgentStatsSerializer,
    DeliveryAgentCreateSerializer,
    DeliveryAgentListSerializer,
    WalletBalanceSerializer,
    WalletTransactionListSerializer,
    WithdrawalRequestSerializer,
    WithdrawalResponseSerializer,
    PaymentSettingsSerializer,
    PaymentSettingsUpdateSerializer,
    PaymentPINSerializer,
    PINResetRequestSerializer,
    PayoutRequestSerializer,
    VendorOrderSummarySerializer,
    VendorOrderListItemSerializer,
    VendorOrderDetailSerializer,
    DisputeResolutionSerializer,
    AdminPaymentSettingsSerializer,
    AdminWithdrawalSerializer,
    AdminWalletBalanceSerializer,
    AdminPaymentPINSerializer
)
from transactions.serializers import PaymentSerializer
from users.services.profile_resolver import ProfileResolver
from transactions.models import PayoutRecord, Order, Payment, OrderStatusHistory
from users.notification_models import Notification
from users.notification_helpers import (
    send_order_notification,
    send_delivery_notification,
    send_user_notification,
    notify_admin,
)
import logging

logger = logging.getLogger(__name__)

class CustomerProfileViewSet(viewsets.ViewSet):
    """
    ViewSet for managing customer profiles and account operations.
    
    Endpoints:
    - GET /api/customer/profile/: Retrieve authenticated customer profile
    - PUT /api/customer/profile/: Update entire customer profile
    - PATCH /api/customer/profile/: Partially update customer profile
    - POST /api/customer/change-password/: Change account password
    """
    permission_classes = [IsAuthenticated]

    def get_customer(self, request):
        """Returns customer profile or None if user is not a customer."""
        return ProfileResolver.resolve_customer(request.user)

    @swagger_auto_schema(
        operation_id="customer_profile_retrieve",
        operation_summary="Retrieve Customer Profile",
        operation_description="Get the authenticated customer's profile information including shipping address, city, country, postal code, and loyalty points.",
        tags=["Customer Profile"],
        responses={
            200: openapi.Response(
                "Customer profile retrieved successfully",
                CustomerProfileSerializer()
            ),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    def list(self, request):
        customer = self.get_customer(request)

        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CustomerProfileSerializer(customer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="customer_profile_update",
        operation_summary="Update Customer Profile (Full)",
        operation_description="Update all fields of the customer profile. All fields must be provided (shipping_address, city, country, postal_code).",
        tags=["Customer Profile"],
        request_body=CustomerProfileUpdateSerializer,
        responses={
            200: openapi.Response(
                "Profile updated successfully",
                CustomerProfileSerializer()
            ),
            400: openapi.Response("Invalid input data"),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    def update(self, request):
        customer = self.get_customer(request)

        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CustomerProfileUpdateSerializer(
            customer,
            data=request.data,
            partial=False,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            CustomerProfileSerializer(customer).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="customer_profile_partial_update",
        operation_summary="Partially Update Customer Profile",
        operation_description="Update specific fields of the customer profile and user info. Can update shipping address, location, contact info, and profile picture. Only provide the fields you want to update.",
        tags=["Customer Profile"],
        request_body=CustomerProfileUpdateSerializer,
        responses={
            200: openapi.Response(
                "Profile updated successfully",
                CustomerProfileSerializer()
            ),
            400: openapi.Response("Invalid input data"),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    def partial_update(self, request):
        customer = self.get_customer(request)

        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CustomerProfileUpdateSerializer(
            customer,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            CustomerProfileSerializer(customer).data,
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="customer_change_password",
        operation_summary="Change Customer Account Password",
        operation_description="Update the authenticated customer's password. Requires current password for verification.",
        tags=["Customer Profile"],
        request_body=ChangePasswordSerializer,
        responses={
            200: openapi.Response("Password changed successfully"),
            400: openapi.Response("Invalid current password or validation error"),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        customer = self.get_customer(request)

        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not user.check_password(serializer.validated_data["current_password"]):
            return Response(
                {"detail": "Incorrect password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save()

        return Response(
            {"message": "Password changed successfully"},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="customer_close_account",
        operation_summary="Close Customer Account",
        operation_description="Permanently close the authenticated customer's account for privacy and security compliance. Account cannot be recovered after closure. Requires password confirmation.",
        tags=["Customer Profile"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='User password for confirmation'),
            },
            required=['password']
        ),
        responses={
            200: openapi.Response("Account closed successfully", 
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: openapi.Response("Invalid password",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["delete"])
    def close_account(self, request):
        """Close the customer account for privacy and security compliance."""
        customer = self.get_customer(request)

        if not customer:
            return Response(
                {"success": False, "error": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        password = request.data.get('password')
        if not password:
            return Response(
                {"success": False, "error": "The password provided is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(password):
            return Response(
                {"success": False, "error": "The password provided is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Soft delete: set is_active to False so user cannot login
        with transaction.atomic():
            user.is_active = False
            user.save(update_fields=['is_active', 'updated_at'])

        return Response(
            {"success": True, "message": "Account closed successfully."},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="customer_delete_account",
        operation_summary="Delete Customer Account",
        operation_description="Permanently delete the authenticated customer's account. This action cannot be undone. Requires password confirmation.",
        tags=["Customer Profile"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='User password for confirmation'),
            },
            required=['password']
        ),
        responses={
            204: openapi.Response("Account deleted successfully"),
            400: openapi.Response("Invalid password"),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def delete_account(self, request):
        """Permanently delete the customer account and all associated data."""
        customer = self.get_customer(request)

        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        password = request.data.get('password')
        if not password:
            return Response(
                {"detail": "Password is required for account deletion"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(password):
            return Response(
                {"detail": "Incorrect password"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete the user account (cascade will delete customer profile)
        user.delete()

        return Response(
            {"message": "Account deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )

    # ============================
    # WALLET & PAYMENT
    # ============================

    @swagger_auto_schema(
        operation_id="customer_wallet_balance",
        operation_summary="Get Wallet Balance",
        operation_description="Retrieve customer's current wallet balance and transaction summary.",
        tags=["Customer Wallet"],
        responses={
            200: openapi.Response(
                "Wallet balance retrieved successfully",
                WalletBalanceSerializer()
            ),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def wallet_balance(self, request):
        """Get wallet balance and transaction summary"""
        customer = self.get_customer(request)
        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Wallet, WalletTransaction
        from django.db.models import Sum
        from django.utils import timezone
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # Calculate totals
        total_credits = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='CREDIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        total_debits = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='DEBIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # This month earnings
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_earnings = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='CREDIT',
            created_at__gte=month_start
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        data = {
            'balance': float(wallet.balance),
            'total_credits': float(total_credits),
            'total_debits': float(total_debits),
            'this_month_earnings': float(this_month_earnings),
        }
        
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="customer_wallet_transactions",
        operation_summary="Get Transaction History",
        operation_description="Retrieve paginated wallet transaction history.",
        tags=["Customer Wallet"],
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=20),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=0),
            openapi.Parameter('type', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='credit or debit'),
        ],
        responses={
            200: openapi.Response(
                "Transactions retrieved successfully",
            ),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def wallet_transactions(self, request):
        """Get wallet transaction history"""
        customer = self.get_customer(request)
        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Wallet, WalletTransaction
        from rest_framework.pagination import LimitOffsetPagination
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # Filter by type if provided
        transactions = WalletTransaction.objects.filter(wallet=wallet)
        txn_type = request.query_params.get('type')
        if txn_type and txn_type.upper() in ['CREDIT', 'DEBIT']:
            transactions = transactions.filter(transaction_type=txn_type.upper())
        
        # Paginate
        paginator = LimitOffsetPagination()
        paginated_txns = paginator.paginate_queryset(
            transactions.order_by('-created_at'),
            request
        )
        
        serializer = WalletTransactionListSerializer(paginated_txns, many=True)
        
        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_id="customer_set_payment_pin",
        operation_summary="Set/Change Payment PIN",
        operation_description="Set or change the 4-digit payment PIN for withdrawals.",
        tags=["Customer Payment Settings"],
        request_body=PaymentPINSerializer,
        responses={
            200: openapi.Response("PIN set successfully"),
            400: openapi.Response("Invalid PIN"),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def set_payment_pin(self, request):
        """Set or change payment PIN"""
        customer = self.get_customer(request)
        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = PaymentPINSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        from users.models import PaymentPIN
        
        # Create or get existing PIN object
        try:
            pin_obj = PaymentPIN.objects.get(user=request.user)
            created = False
        except PaymentPIN.DoesNotExist:
            pin_obj = PaymentPIN()
            pin_obj.user = request.user
            created = True
        
        # Hash and set the PIN (automatically marks as non-default if not 0000)
        pin_obj.set_pin(serializer.validated_data['pin'])
        
        message = "PIN set successfully" if created else "PIN changed successfully"
        return Response(
            {"success": True, "message": message},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="customer_request_withdrawal",
        operation_summary="Request Withdrawal",
        operation_description="Initiate a withdrawal request from customer's wallet balance.",
        tags=["Customer Wallet"],
        request_body=WithdrawalRequestSerializer,
        responses={
            200: openapi.Response(
                "Withdrawal request submitted",
                WithdrawalResponseSerializer()
            ),
            400: openapi.Response("Invalid request"),
            403: openapi.Response("Customer access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def request_withdrawal(self, request):
        """Request a withdrawal"""
        customer = self.get_customer(request)
        if not customer:
            return Response(
                {"detail": "Customer access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = WithdrawalRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        amount = serializer.validated_data['amount']
        pin = serializer.validated_data['pin']
        
        # Validate withdrawal request
        is_valid, error_msg = PayoutService.validate_withdrawal_request(request.user, amount)
        if not is_valid:
            return Response(
                {"success": False, "message": error_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Verify PIN
        pin_valid, pin_error = PayoutService.verify_pin(request.user, pin)
        if not pin_valid:
            return Response(
                {"success": False, "message": pin_error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Get customer's bank details from request
        bank_name = request.data.get('bank_name', '')
        account_number = request.data.get('account_number', '')
        account_name = request.data.get('account_name', '')
        
        if not all([bank_name, account_number, account_name]):
            return Response(
                {"success": False, "message": "Bank details (bank_name, account_number, account_name) are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Create withdrawal request with admin notification
        payout, error = PayoutService.create_withdrawal_request(
            user=request.user,
            amount=amount,
            bank_name=bank_name,
            account_number=account_number,
            account_name=account_name,
            vendor=None
        )
        
        if error:
            return Response(
                {"success": False, "message": error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        message = f"Withdrawal request of ₦{amount:,.2f} is being processed. Reference: {payout.reference}"
        return Response(
            {"success": True, "message": message, "reference": payout.reference},
            status=status.HTTP_200_OK,
        )




class VendorViewSet(viewsets.ViewSet):
    """
    ViewSet for managing vendor profiles, products, orders, and analytics.
    
    Endpoints include profile management, product CRUD operations, order tracking,
    sales analytics, and notification retrieval.
    """
    permission_classes = [IsAuthenticated]

    def get_vendor(self, request):
        """Returns vendor profile or None if user is not a vendor."""
        return ProfileResolver.resolve_vendor(request.user)

    # ============================
    # PROFILE MANAGEMENT
    # ============================

    @swagger_auto_schema(
        operation_id="vendor_profile_retrieve",
        operation_summary="Retrieve Vendor Profile",
        operation_description="Get the authenticated vendor's complete profile information including store details, bank information, and verification status.",
        tags=["Vendor Profile"],
        responses={
            200: openapi.Response(
                "Vendor profile retrieved successfully",
                VendorProfileSerializer()
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def retrieve(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = ProfileService.get_profile(
            user=request.user,
            request=request,
        )

        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="vendor_profile_update",
        operation_summary="Update Vendor Profile (Full)",
        operation_description="Update all vendor profile fields. All required fields must be provided.",
        tags=["Vendor Profile"],
        request_body=VendorProfileSerializer,
        responses={
            200: openapi.Response(
                "Profile updated successfully",
                VendorProfileSerializer()
            ),
            400: openapi.Response("Invalid input data"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def update(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        success, data, code = ProfileService.update_profile(
            user=request.user,
            data=request.data,
            files=request.FILES,
            request=request,
            partial=False,
        )

        return Response(data, status=code)

    @swagger_auto_schema(
        operation_id="vendor_profile_partial_update",
        operation_summary="Partially Update Vendor Profile",
        operation_description="Update specific vendor profile fields. Only provide the fields you want to change.",
        tags=["Vendor Profile"],
        request_body=VendorProfileSerializer,
        responses={
            200: openapi.Response(
                "Profile updated successfully",
                VendorProfileSerializer()
            ),
            400: openapi.Response("Invalid input data"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def partial_update(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        success, data, code = ProfileService.update_profile(
            user=request.user,
            data=request.data,
            files=request.FILES,
            request=request,
            partial=True,
        )

        return Response(data, status=code)

    @swagger_auto_schema(
        method="post",
        operation_id="vendor_change_password",
        operation_summary="Change Vendor Account Password",
        operation_description="Update the vendor's password. Requires current password for verification.",
        tags=["Vendor Profile"],
        request_body=ChangePasswordSerializer,
        responses={
            200: openapi.Response("Password changed successfully"),
            400: openapi.Response("Invalid current password"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = ProfileService.process_password_change(
            request.user,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )

        return Response(
            result,
            status=status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST,
        )

    @swagger_auto_schema(
        operation_id="vendor_close_account",
        operation_summary="Close Vendor Account",
        operation_description="Permanently close the authenticated vendor's account and store for privacy and security compliance. All products will be marked as inactive. Account cannot be recovered after closure. Requires password confirmation.",
        tags=["Vendor Profile"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Vendor password for confirmation'),
            },
            required=['password']
        ),
        responses={
            200: openapi.Response("Account closed successfully", 
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'message': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            400: openapi.Response("Invalid password",
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        'error': openapi.Schema(type=openapi.TYPE_STRING),
                    }
                )
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["delete"])
    def close_account(self, request):
        """Close the vendor account and store for privacy and security compliance."""
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "error": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        password = request.data.get('password')
        if not password:
            return Response(
                {"success": False, "error": "The password provided is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(password):
            return Response(
                {"success": False, "error": "The password provided is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Soft delete vendor and mark all products as inactive
        with transaction.atomic():
            from store.models import Product
            
            # Mark all vendor's products as inactive
            Product.objects.filter(store=vendor).update(publish_status='draft')
            
            # Set user as inactive so they cannot login
            user.is_active = False
            user.save(update_fields=['is_active', 'updated_at'])

        return Response(
            {"success": True, "message": "Vendor account and store have been closed successfully."},
            status=status.HTTP_200_OK,
        )

    # ============================
    # PRODUCT MANAGEMENT
    # ============================

    @swagger_auto_schema(
        method="post",
        operation_id="vendor_add_product",
        operation_summary="Add New Product to Store",
        operation_description="Create a new product listing for the vendor's store. Returns the created product with all details.",
        tags=["Vendor Products"],
        request_body=CreateProductSerializer,
        responses={
            201: openapi.Response(
                "Product created successfully",
                CreateProductSerializer()
            ),
            400: openapi.Response("Invalid product data"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def add_product(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CreateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Create product directly with submitted status for admin review
        serializer.save(store=vendor, publish_status='submitted', approval_status='pending')

        return Response(
            {"success": True, "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    @swagger_auto_schema(
        method="get",
        operation_id="vendor_list_products",
        operation_summary="List Vendor's Products",
        operation_description="Retrieve all products in the vendor's store with their details, pricing, and status.",
        tags=["Vendor Products"],
        responses={
            200: openapi.Response(
                "Products retrieved successfully",
                ProductSerializer(many=True)
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_products(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Only return submitted products (not drafts)
        products = Product.objects.filter(store=vendor, publish_status='submitted')
        serializer = ProductSerializer(products, many=True)

        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        method="put",
        operation_summary="Update Product (Full)",
        operation_description="Fully update a product's information. All fields must be provided.",
        tags=["Vendor Products"],
        request_body=ProductSerializer,
        responses={
            200: openapi.Response(
                "Product updated successfully",
                ProductSerializer()
            ),
            400: openapi.Response("Invalid product data"),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @swagger_auto_schema(
        method="patch",
        operation_summary="Update Product (Partial)",
        operation_description="Partially update a product's information. Only provide fields you want to change.",
        tags=["Vendor Products"],
        request_body=ProductSerializer,
        responses={
            200: openapi.Response(
                "Product updated successfully",
                ProductSerializer()
            ),
            400: openapi.Response("Invalid product data"),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["put", "patch"])
    def update_product(self, request, pk=None):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            # Only allow updates to submitted products (not drafts)
            product = Product.objects.get(pk=pk, store=vendor, publish_status='submitted')
        except Product.DoesNotExist:
            return Response(
                {"success": False, "message": "Product not found or not a submitted product"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProductSerializer(
            product,
            data=request.data,
            partial=request.method.lower() == "patch",
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        method="delete",
        operation_id="vendor_delete_product",
        operation_summary="Delete Product",
        operation_description="Remove a product from the vendor's store. Once deleted, the product is no longer available for purchase.",
        tags=["Vendor Products"],
        responses={
            200: openapi.Response("Product deleted successfully"),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["delete"])
    def delete_product(self, request, pk=None):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            # Only allow deletion of submitted products (not drafts)
            product = Product.objects.get(pk=pk, store=vendor, publish_status='submitted')
            product.delete()
        except Product.DoesNotExist:
            return Response(
                {"success": False, "message": "Product not found or not a submitted product"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"success": True, "message": "Product deleted"},
            status=status.HTTP_200_OK,
        )

    # ============================
    # ORDER MANAGEMENT
    # ============================
    @swagger_auto_schema(
        method="get",
        operation_id="vendor_orders_summary",
        operation_summary="Get Vendor Orders Summary",
        operation_description="Get a count of vendor's orders grouped by status (pending, paid, shipped, delivered, canceled).",
        tags=["Vendor Orders"],
        responses={
            200: openapi.Response(
                "Orders summary retrieved successfully",
                VendorOrdersSummaryResponseSerializer()
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def orders(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from transactions.models import Order

        # Get distinct order IDs for this vendor
        order_ids = Order.objects.filter(
            order_items__product__store=vendor
        ).values_list('order_id', flat=True).distinct()
        
        orders = Order.objects.filter(order_id__in=order_ids)

        data = {
            "pending": orders.filter(status=Order.Status.PENDING).count(),
            "paid": orders.filter(status=Order.Status.PAID).count(),
            "shipped": orders.filter(status=Order.Status.SHIPPED).count(),
            "delivered": orders.filter(status=Order.Status.DELIVERED).count(),
            "canceled": orders.filter(status=Order.Status.CANCELED).count(),
        }

        serializer = VendorOrderSummarySerializer(data)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_id="vendor_orders_list",
        operation_summary="List Vendor Orders",
        operation_description="Get paginated list of vendor's orders with optional filtering and sorting.",
        tags=["Vendor Orders"],
        manual_parameters=[
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description='Number of results to return per page',
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description='Number of results to skip',
                type=openapi.TYPE_INTEGER,
                required=False,
            ),
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description='Filter by order status (PENDING, PAID, SHIPPED, DELIVERED, CANCELED)',
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                'ordering',
                openapi.IN_QUERY,
                description='Sort results. Default: -created_at (newest first). Use -created_at or created_at',
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response(
                "Orders retrieved successfully",
                VendorOrderListItemSerializer(many=True)
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def list_orders(self, request):
        """Get paginated list of vendor's orders"""
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from transactions.models import Order
        from rest_framework.pagination import LimitOffsetPagination

        # Get distinct order IDs for this vendor's products
        order_ids = Order.objects.filter(
            order_items__product__store=vendor
        ).values_list('order_id', flat=True).distinct()
        
        logger.info(f"Vendor {vendor.uuid} - Found {len(order_ids)} orders with their products")

        # Fetch full orders with optimized queries
        orders = Order.objects.filter(
            order_id__in=order_ids
        ).select_related('customer').prefetch_related('order_items__product')

        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            orders = orders.filter(status=status_filter)

        # Sort orders - default by -ordered_at (newest first)
        ordering = request.query_params.get('ordering', '-ordered_at')
        try:
            orders = orders.order_by(ordering)
        except Exception as e:
            logger.error(f"Invalid ordering parameter: {ordering}. Error: {str(e)}")
            orders = orders.order_by('-ordered_at')

        # Paginate results
        paginator = LimitOffsetPagination()
        paginated_orders = paginator.paginate_queryset(orders, request)

        # Serialize and return
        serializer = VendorOrderListItemSerializer(paginated_orders, many=True)
        
        if paginated_orders is not None:
            paginated_data = {
                "count": paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data
            }
            return Response(standardized_response(data=paginated_data))
        else:
            return Response(standardized_response(data=serializer.data))

    @swagger_auto_schema(
        operation_id="vendor_order_detail",
        operation_summary="Get Vendor Order Details",
        operation_description="Get complete details for a specific order including itemized list of products.",
        tags=["Vendor Orders"],
        responses={
            200: openapi.Response(
                "Order details retrieved successfully",
                VendorOrderDetailSerializer()
            ),
            403: openapi.Response("Vendor access only"),
            404: openapi.Response("Order not found"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"], url_path=r"(?P<order_uuid>[^/.]+)")
    def order_detail(self, request, order_uuid=None):
        """Get detailed information for a specific order"""
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from transactions.models import Order

        try:
            # Get the order and ensure vendor has products in it
            order = Order.objects.filter(
                order_items__product__store=vendor,
                order_id=order_uuid
            ).select_related('customer').prefetch_related('order_items__product').first()

            if not order:
                return Response(
                    {"success": False, "message": "Order not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = VendorOrderDetailSerializer(order)
            return Response({"success": True, "data": serializer.data})

        except Exception as e:
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # ============================
    # ANALYTICS & INSIGHTS
    # ============================

    @swagger_auto_schema(
        method="get",
        operation_id="vendor_analytics",
        operation_summary="Get Vendor Sales Analytics",
        operation_description="Retrieve vendor's total revenue and top 5 best-selling products with quantity sold.",
        tags=["Vendor Analytics"],
        responses={
            200: openapi.Response(
                "Analytics data retrieved successfully",
                VendorAnalyticsResponseSerializer()
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def analytics(self, request):
        vendor = self.get_vendor(request)

        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from transactions.models import OrderItem
        from django.db.models import Sum, F

        items = OrderItem.objects.filter(product__store=vendor)

        total_revenue = (
            items.aggregate(
                total=Sum(F("product__price") * F("quantity"))
            )["total"]
            or 0
        )

        product_stats = (
            items.values("product__name")
            .annotate(sold=Sum("quantity"))
            .order_by("-sold")[:5]
        )

        return Response(
            {
                "success": True,
                "data": {
                    "total_revenue": total_revenue,
                    "top_products": product_stats,
                },
            }
        )

    # ============================
    # NOTIFICATIONS
    # ============================

    @swagger_auto_schema(
        method="get",
        operation_id="vendor_notifications",
        operation_summary="List Vendor Notifications",
        operation_description="Retrieve all notifications for the vendor, ordered by most recent first.",
        tags=["Vendor Notifications"],
        responses={
            200: openapi.Response(
                "Notifications retrieved successfully",
                NotificationSerializer(many=True)
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def notifications(self, request):
        notifications = Notification.objects.filter(
            user=request.user
        ).order_by("-created_at")

        serializer = NotificationSerializer(notifications, many=True)
        return Response({"success": True, "data": serializer.data})



import uuid
from decimal import Decimal
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from users.services.profile_resolver import ProfileResolver
from .serializers import (
    AdminUserManagementSerializer,
    ChangePasswordSerializer,
    VendorProfileSerializer,
    NotificationSerializer,
)
from users.services.services import ProfileService, AdminService
from users.models import Vendor, Customer
from transactions.models import Order, Refund, Wallet
from transactions.models import Payment, TransactionLog
from users.notification_models import Notification
from store.models import Product
from django.db import models
from users.serializers import VendorApprovalSerializer
from django.contrib.auth import get_user_model
User = get_user_model()
from authentication.models import CustomUser
from users.serializers import TriggerPayoutSerializer, OrderActionSerializer, AdminProductUpdateSerializer, VendorKYCSerializer, SuspendUserSerializer, BusinessAdminProfileSerializer
from users.services.payout_service import PayoutService

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from users.services.profile_resolver import ProfileResolver


# ============================
# VENDOR WALLET & PAYMENT VIEWS
# ============================

class VendorWalletViewSet(viewsets.ViewSet):
    """
    ViewSet for managing vendor wallet, transactions, and withdrawals.
    """
    permission_classes = [IsAuthenticated]

    def get_vendor(self, request):
        """Returns vendor profile or None if user is not a vendor."""
        return ProfileResolver.resolve_vendor(request.user)

    @swagger_auto_schema(
        operation_id="vendor_wallet_balance",
        operation_summary="Get Wallet Balance",
        operation_description="Retrieve vendor's current wallet balance and earnings summary.",
        tags=["Vendor Wallet"],
        responses={
            200: openapi.Response(
                "Wallet balance retrieved successfully",
                WalletBalanceSerializer()
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def wallet_balance(self, request):
        """Get wallet balance and earnings summary with available vs pending breakdown"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Wallet, WalletTransaction
        from django.db.models import Sum
        from django.utils import timezone
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # Calculate available and pending balances
        available_balance = vendor.get_available_balance()
        pending_balance = vendor.get_pending_balance()
        total_earnings = vendor.get_total_earnings()
        
        # Calculate totals
        total_credits = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='CREDIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        total_debits = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='DEBIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # This month earnings (from completed deliveries)
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_earnings = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='CREDIT',
            created_at__gte=month_start
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Count total withdrawals
        from users.models import PayoutRequest
        total_withdrawals = PayoutRequest.objects.filter(
            vendor=vendor,
            status='successful'
        ).count()
        
        # Get pending order count
        pending_order_count = vendor.get_pending_order_count()
        
        data = {
            'withdrawable_balance': float(available_balance),
            'available_balance': float(available_balance),
            'pending_balance': float(pending_balance),
            'pending_order_count': pending_order_count,
            'total_earnings': float(total_earnings),
            'total_credits': float(total_credits),
            'total_debits': float(total_debits),
            'total_withdrawals': total_withdrawals,
            'this_month_earnings': float(this_month_earnings),
        }
        
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="vendor_wallet_transactions",
        operation_summary="Get Transaction History",
        operation_description="Retrieve paginated wallet transaction history.",
        tags=["Vendor Wallet"],
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=20),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=0),
            openapi.Parameter('type', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='credit or debit'),
        ],
        responses={
            200: openapi.Response(
                "Transactions retrieved successfully",
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def wallet_transactions(self, request):
        """Get wallet transaction history"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Wallet, WalletTransaction
        from rest_framework.pagination import LimitOffsetPagination
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # Filter by type if provided
        transactions = WalletTransaction.objects.filter(wallet=wallet)
        txn_type = request.query_params.get('type')
        if txn_type and txn_type.upper() in ['CREDIT', 'DEBIT']:
            transactions = transactions.filter(transaction_type=txn_type.upper())
        
        # Paginate
        paginator = LimitOffsetPagination()
        paginated_txns = paginator.paginate_queryset(
            transactions.order_by('-created_at'),
            request
        )
        
        serializer = WalletTransactionListSerializer(paginated_txns, many=True)
        
        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_id="vendor_request_withdrawal",
        operation_summary="Request Withdrawal",
        operation_description="Initiate a withdrawal request to vendor's bank account.",
        tags=["Vendor Wallet"],
        request_body=WithdrawalRequestSerializer,
        responses={
            200: openapi.Response(
                "Withdrawal request submitted",
                WithdrawalResponseSerializer()
            ),
            400: openapi.Response("Invalid request"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def request_withdrawal(self, request):
        """Request a withdrawal"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = WithdrawalRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        amount = serializer.validated_data['amount']
        pin = serializer.validated_data['pin']
        
        # Validate withdrawal request
        is_valid, error_msg = PayoutService.validate_withdrawal_request(request.user, amount)
        if not is_valid:
            return Response(
                {"success": False, "message": error_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Verify PIN
        pin_valid, pin_error = PayoutService.verify_pin(request.user, pin)
        if not pin_valid:
            return Response(
                {"success": False, "message": pin_error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Create withdrawal request with admin notification
        payout, error = PayoutService.create_withdrawal_request(
            user=request.user,
            amount=amount,
            bank_name=vendor.bank_name,
            account_number=vendor.account_number,
            account_name=vendor.account_name or '',
            recipient_code=vendor.recipient_code or '',
            vendor=vendor
        )
        
        if error:
            return Response(
                {"success": False, "message": error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        message = f"Withdrawal request of ₦{amount:,.2f} is being processed. Reference: {payout.reference}"
        return Response(
            {"success": True, "message": message, "reference": payout.reference},
            status=status.HTTP_200_OK,
        )


class VendorPaymentSettingsViewSet(viewsets.ViewSet):
    """
    ViewSet for managing vendor payment settings and PIN.
    """
    permission_classes = [IsAuthenticated]

    def get_vendor(self, request):
        """Returns vendor profile or None if user is not a vendor."""
        return ProfileResolver.resolve_vendor(request.user)

    @swagger_auto_schema(
        operation_id="vendor_payment_settings_get",
        operation_summary="Get Payment Settings",
        operation_description="Retrieve vendor's payment settings and bank account details.",
        tags=["Vendor Payment Settings"],
        responses={
            200: openapi.Response(
                "Payment settings retrieved",
                PaymentSettingsSerializer()
            ),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def payment_settings(self, request):
        """Get payment settings"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = PaymentSettingsSerializer(vendor)
        return Response(
            {"success": True, "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="vendor_payment_settings_update",
        operation_summary="Update Payment Settings",
        operation_description="Update vendor's bank account details.",
        tags=["Vendor Payment Settings"],
        request_body=PaymentSettingsUpdateSerializer,
        responses={
            200: openapi.Response("Settings updated successfully"),
            400: openapi.Response("Invalid data"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def update_payment_settings(self, request):
        """Update payment settings"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = PaymentSettingsUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Update vendor fields
        if 'bank_name' in serializer.validated_data:
            vendor.bank_name = serializer.validated_data['bank_name']
        if 'account_number' in serializer.validated_data:
            vendor.account_number = serializer.validated_data['account_number']
        if 'account_name' in serializer.validated_data:
            vendor.account_name = serializer.validated_data['account_name']
        
        vendor.save()
        
        return Response(
            {"success": True, "message": "Payment settings updated successfully"},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="vendor_set_payment_pin",
        operation_summary="Set/Change Payment PIN",
        operation_description="Set or change the 4-digit payment PIN for withdrawals.",
        tags=["Vendor Payment Settings"],
        request_body=PaymentPINSerializer,
        responses={
            200: openapi.Response("PIN set successfully"),
            400: openapi.Response("Invalid PIN"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def set_payment_pin(self, request):
        """Set or change payment PIN"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = PaymentPINSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        from users.models import PaymentPIN
        
        # Create or get existing PIN object
        try:
            pin_obj = PaymentPIN.objects.get(user=request.user)
            created = False
        except PaymentPIN.DoesNotExist:
            pin_obj = PaymentPIN()
            pin_obj.user = request.user
            created = True
        
        # Hash and set the PIN (automatically marks as non-default if not 0000)
        pin_obj.set_pin(serializer.validated_data['pin'])
        
        message = "PIN set successfully" if created else "PIN changed successfully"
        return Response(
            {"success": True, "message": message},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="vendor_forgot_payment_pin",
        operation_summary="Request PIN Reset",
        operation_description="Send a PIN reset link to the vendor's registered email.",
        tags=["Vendor Payment Settings"],
        responses={
            200: openapi.Response("Reset link sent"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def forgot_payment_pin(self, request):
        """Request PIN reset"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # TODO: In production, generate a token and send reset email
        # For now, just send a success response
        
        return Response(
            {
                "success": True,
                "message": "A PIN reset link has been sent to your email."
            },
            status=status.HTTP_200_OK,
        )


class VendorAccountViewSet(viewsets.ViewSet):
    """
    ViewSet for vendor account management operations.
    """
    permission_classes = [IsAuthenticated]

    def get_vendor(self, request):
        """Returns vendor profile or None if user is not a vendor."""
        return ProfileResolver.resolve_vendor(request.user)

    @swagger_auto_schema(
        operation_id="vendor_delete_account",
        operation_summary="Delete Vendor Account",
        operation_description="Permanently delete the vendor account. Requires password confirmation.",
        tags=["Vendor Account"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'password': openapi.Schema(type=openapi.TYPE_STRING, description='Current password'),
            },
            required=['password']
        ),
        responses={
            204: openapi.Response("Account deleted successfully"),
            400: openapi.Response("Invalid password"),
            403: openapi.Response("Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    def delete_account(self, request):
        """Delete vendor account"""
        vendor = self.get_vendor(request)
        if not vendor:
            return Response(
                {"success": False, "message": "Vendor access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Verify password
        password = request.data.get('password')
        if not password:
            return Response(
                {"success": False, "message": "Password is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if not request.user.check_password(password):
            return Response(
                {"success": False, "message": "Invalid password"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Delete user and related data (cascade)
        user = request.user
        user.delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminBaseViewSet(viewsets.ViewSet):
    """
    Base ViewSet for admin operations with common permission and admin validation.
    """
    permission_classes = [IsAuthenticated]

    def get_admin(self, request):
        """Verify user is admin and return admin profile."""
        admin = ProfileResolver.resolve_admin(request.user)
        if not admin:
            return None
        return admin

    def get_user_by_uuid(self, user_uuid):
        """Retrieve user by UUID."""
        return User.objects.filter(uuid=user_uuid).first()


class AdminProfileViewSet(AdminBaseViewSet):
    """
    ViewSet for managing admin profile and account settings.
    """

    @swagger_auto_schema(
        operation_id="admin_profile_retrieve",
        operation_summary="Retrieve Business Admin Profile",
        operation_description="Get the authenticated admin's profile information including position and management permissions.",
        tags=["Admin Profile"],
        responses={
            200: openapi.Response(
                "Admin profile retrieved successfully",
                BusinessAdminProfileSerializer()
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    def retrieve(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = BusinessAdminProfileSerializer(admin)

        return Response({
            "success": True,
            "data": serializer.data
        })

    @swagger_auto_schema(
        operation_id="admin_change_password",
        operation_summary="Change Admin Account Password",
        operation_description="Update the admin's password. Requires current password for verification.",
        tags=["Admin Profile"],
        request_body=ChangePasswordSerializer,
        responses={
            200: openapi.Response("Password changed successfully"),
            400: openapi.Response("Invalid current password"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = ProfileService.process_password_change(
            request.user,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )

        status_code = 200 if result.get("success") else 400
        return Response(result, status=status_code)


class AdminVendorViewSet(AdminBaseViewSet):
    """
    ViewSet for admin vendor management operations including approval, suspension, and KYC verification.
    """

    @swagger_auto_schema(
        operation_id="admin_list_vendors",
        operation_summary="List All Vendors",
        operation_description="Retrieve a list of all vendors on the platform with their store information and verification status.",
        tags=["Vendor Management"],
        responses={
            200: openapi.Response(
                "Vendors retrieved successfully",
                AdminVendorListSerializer(many=True)
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_vendors(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        vendors = Vendor.objects.select_related("user").all()
        serializer = AdminVendorListSerializer(vendors, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_id="admin_vendor_details",
        operation_summary="Get Individual Vendor Details",
        operation_description="Retrieve detailed information about a specific vendor including store details, KYC information, and account status.",
        tags=["Vendor Management"],
        responses={
            200: openapi.Response(
                "Vendor details retrieved successfully",
                AdminVendorDetailSerializer()
            ),
            404: openapi.Response("Vendor not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"], url_path="(?P<vendor_uuid>[^/.]+)")
    def get_vendor_details(self, request, vendor_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        if not vendor_uuid:
            return Response({"message": "Vendor UUID is required"}, status=400)

        try:
            vendor = Vendor.objects.select_related("user").get(user__uuid=vendor_uuid)
            serializer = AdminVendorDetailSerializer(vendor)
            return Response({"success": True, "data": serializer.data})
        except Vendor.DoesNotExist:
            return Response({"message": "Vendor not found"}, status=404)

    @swagger_auto_schema(
        operation_id="admin_approve_vendor",
        operation_summary="Approve or Unapprove Vendor",
        operation_description="Approve or revoke approval for a vendor. Requires vendor UUID and approval boolean flag.",
        tags=["Vendor Management"],
        request_body=AdminVendorApprovalSerializer,
        responses={
            200: openapi.Response(
                "Vendor approval status updated",
                AdminVendorActionResponseSerializer()
            ),
            400: openapi.Response("Invalid request data"),
            404: openapi.Response("Vendor not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def approve_vendor(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminVendorApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_user_by_uuid(serializer.validated_data["user_uuid"])
        if not user or not hasattr(user, "vendor_profile"):
            return Response({"message": "Vendor not found"}, status=404)

        approve = serializer.validated_data["approve"]
        user.vendor_profile.is_verified_vendor = approve
        user.vendor_profile.save(update_fields=["is_verified_vendor"])

        user.is_verified = approve
        user.save(update_fields=["is_verified"])

        response_serializer = AdminVendorActionResponseSerializer({"success": True, "approved": approve})
        return Response(response_serializer.data)

    @swagger_auto_schema(
        operation_id="admin_suspend_user",
        operation_summary="Suspend or Activate User",
        operation_description="Suspend (deactivate) or activate a user account. Suspended users cannot access the platform.",
        tags=["Vendor Management"],
        request_body=AdminVendorSuspendSerializer,
        responses={
            200: openapi.Response(
                "User status updated",
                AdminVendorActionResponseSerializer()
            ),
            400: openapi.Response("Invalid request data"),
            404: openapi.Response("User not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def suspend_user(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminVendorSuspendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_user_by_uuid(serializer.validated_data["user_uuid"])
        if not user:
            return Response({"message": "User not found"}, status=404)

        suspend = serializer.validated_data["suspend"]
        user.is_active = not suspend
        user.save(update_fields=["is_active"])

        response_serializer = AdminVendorActionResponseSerializer({"success": True, "suspended": suspend})
        return Response(response_serializer.data)

    @swagger_auto_schema(
        operation_id="admin_verify_kyc",
        operation_summary="Verify Vendor KYC",
        operation_description="Mark a vendor's KYC (Know Your Customer) documentation as verified.",
        tags=["Vendor Management"],
        request_body=AdminVendorKYCSerializer,
        responses={
            200: openapi.Response(
                "KYC verification completed",
                AdminVendorActionResponseSerializer()
            ),
            400: openapi.Response("Invalid request data"),
            404: openapi.Response("Vendor not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def verify_kyc(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminVendorKYCSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_user_by_uuid(serializer.validated_data["user_uuid"])
        if not user or not hasattr(user, "vendor_profile"):
            return Response({"message": "Vendor not found"}, status=404)

        user.vendor_profile.is_verified_vendor = True
        user.vendor_profile.save(update_fields=["is_verified_vendor"])

        response_serializer = AdminVendorActionResponseSerializer({
            "success": True,
            "message": "Vendor KYC verified"
        })
        return Response(response_serializer.data)


class AdminMarketplaceViewSet(AdminBaseViewSet):
    """
    ViewSet for admin management of marketplace products including listing, updating, and deletion.
    """

    @swagger_auto_schema(
        operation_id="admin_list_products",
        operation_summary="List All Marketplace Products",
        operation_description="Retrieve all products available on the marketplace with vendor information.",
        tags=["Marketplace Management"],
        responses={
            200: openapi.Response(
                "Products retrieved successfully",
                AdminProductListSerializer(many=True)
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_products(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        products = Product.objects.select_related("store").all()
        serializer = AdminProductListSerializer(products, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_id="admin_product_detail",
        operation_summary="Get Product Details",
        operation_description="Retrieve detailed information about a specific product including all pricing, inventory, and approval details.",
        tags=["Marketplace Management"],
        manual_parameters=[openapi.Parameter("slug", openapi.IN_QUERY, description="Product slug identifier", type=openapi.TYPE_STRING, required=True)],
        responses={
            200: openapi.Response(
                "Product details retrieved successfully",
                AdminProductDetailSerializer()
            ),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def product_detail(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        slug = request.query_params.get('slug')
        if not slug:
            return Response({"success": False, "message": "Product slug is required"}, status=400)

        try:
            product = Product.objects.select_related("store", "category", "approved_by").get(slug=slug)
        except Product.DoesNotExist:
            return Response({"success": False, "message": "Product not found"}, status=404)

        serializer = AdminProductDetailSerializer(product)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        method='put',
        operation_id="admin_update_product_full",
        operation_summary="Update Product (Full)",
        operation_description="Fully update a product's details. All fields must be provided.",
        tags=["Marketplace Management"],
        request_body=AdminProductUpdateSerializer,
        responses={
            200: openapi.Response("Product updated successfully"),
            400: openapi.Response("Invalid product data"),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @swagger_auto_schema(
        method='patch',
        operation_id="admin_update_product_partial",
        operation_summary="Update Product (Partial)",
        operation_description="Partially update a product's details. Only provide fields you want to change.",
        tags=["Marketplace Management"],
        request_body=AdminProductUpdateSerializer,
        responses={
            200: openapi.Response("Product updated successfully"),
            400: openapi.Response("Invalid product data"),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["put", "patch"])
    def update_product(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminProductUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success, data = AdminService.update_product(
            serializer.validated_data["product_uuid"],
            serializer.validated_data
        )

        return Response({"success": success, "data": data}, status=200 if success else 400)

    @swagger_auto_schema(
        operation_id="admin_delete_product",
        operation_summary="Delete Product",
        operation_description="Remove a product from the marketplace. Deleted products cannot be restored.",
        tags=["Marketplace Management"],
        manual_parameters=[openapi.Parameter("slug", openapi.IN_PATH, description="Product slug identifier", type=openapi.TYPE_STRING)],
        responses={
            200: openapi.Response(
                "Product deleted successfully",
                AdminProductActionResponseSerializer()
            ),
            400: openapi.Response("Invalid request"),
            404: openapi.Response("Product not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["delete"], url_path='delete_product/(?P<slug>[^/.]+)')
    def delete_product(self, request, slug=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        if not slug:
            return Response({"success": False, "message": "Product slug is required"}, status=400)

        product = Product.objects.filter(slug=slug).first()
        if not product:
            return Response({"success": False, "message": "Product not found"}, status=404)

        product.delete()
        response_serializer = AdminProductActionResponseSerializer({
            "success": True,
            "message": f"Product '{slug}' deleted successfully"
        })
        return Response(response_serializer.data)


class AdminOrdersViewSet(AdminBaseViewSet):
    """
    ViewSet for admin management of orders, including order logistics and refund processing.
    """

    @swagger_auto_schema(
        operation_id="admin_orders_summary",
        operation_summary="Get Orders Summary",
        operation_description="Retrieve a summary of all platform orders grouped by status (pending, shipped, delivered).",
        tags=["Orders & Logistics"],
        responses={
            200: openapi.Response(
                "Orders summary retrieved successfully",
                AdminOrdersSummarySerializer()
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        data = {
            "pending": Order.objects.filter(status="pending").count(),
            "shipped": Order.objects.filter(status="shipped").count(),
            "delivered": Order.objects.filter(status="delivered").count(),
        }
        serializer = AdminOrdersSummarySerializer(data)
        return Response({"success": True, "data": data})

    @swagger_auto_schema(
        operation_id="admin_assign_logistics",
        operation_summary="Assign Logistics/Delivery Agent to Order",
        operation_description="Assign a delivery agent to an order. Delivery agent will receive notification.",
        tags=["Orders & Logistics"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING, description='Order UUID'),
                'delivery_agent_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Delivery Agent ID')
            },
            required=['order_id', 'delivery_agent_id']
        ),
        responses={
            200: openapi.Response("Delivery agent assigned successfully"),
            400: openapi.Response("Invalid request data"),
            404: openapi.Response("Order or delivery agent not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def assign_logistics(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = DeliveryAgentAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = Order.objects.get(order_id=serializer.validated_data['order_id'])
        except Order.DoesNotExist:
            return Response({"success": False, "message": "Order not found"}, status=404)

        from users.models import DeliveryAgent
        try:
            delivery_agent = DeliveryAgent.objects.get(id=serializer.validated_data['delivery_agent_id'])
        except DeliveryAgent.DoesNotExist:
            return Response({"success": False, "message": "Delivery agent not found"}, status=404)

        order.delivery_agent = delivery_agent
        order.assigned_at = timezone.now()
        order.save(update_fields=['delivery_agent', 'assigned_at'])

        # Notify delivery agent
        send_delivery_notification(
            delivery_agent.user,
            "New Order Assignment",
            f"You have been assigned order {order.order_id} for delivery.",
            order_id=order.order_id
        )

        # Notify customer
        send_order_notification(
            order.customer,
            "Delivery Agent Assigned",
            f"A delivery agent has been assigned to your order {order.order_id}.",
            order_id=order.order_id
        )

        return Response({
            "success": True,
            "message": "Delivery agent assigned successfully",
            "order_id": str(order.order_id),
            "delivery_agent": delivery_agent.user.full_name
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="admin_mark_order_shipped",
        operation_summary="Mark Order as SHIPPED",
        operation_description="""Mark an order as SHIPPED (Step 9 in order flow).
        
Flow Step: 8 → 9
- Vendors AND Admins notified of new order
- Admin or Vendor marks as SHIPPED
- Customer notified of shipment
        
This action:
- Updates order status to SHIPPED
- Records timestamp when order was shipped
- Sends notification to customer
- Creates audit trail with OrderStatusHistory

Access: Admin (staff) or Vendor (who owns items in order)""",
        tags=["Orders & Logistics"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING, description='Order UUID'),
                'tracking_number': openapi.Schema(type=openapi.TYPE_STRING, description='Optional shipment tracking number'),
            },
            required=['order_id']
        ),
        responses={
            200: openapi.Response("Order marked as shipped successfully"),
            400: openapi.Response("Invalid request or order not in PAID status"),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Admin/Vendor access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def mark_shipped(self, request):
        # Check permissions - admin/staff or vendor
        is_admin = request.user.is_staff if request.user else False
        is_vendor = hasattr(request.user, 'store') if request.user else False
        
        if not is_admin and not is_vendor:
            return Response({"message": "Access denied - Admin or Vendor only"}, status=403)

        try:
            order = Order.objects.get(order_id=request.data.get('order_id'))
        except Order.DoesNotExist:
            return Response({"success": False, "message": "Order not found"}, status=404)

        # Verify order is in PAID status
        if order.status != Order.Status.PAID:
            return Response({
                "success": False, 
                "message": f"Order must be in PAID status to mark as SHIPPED. Current status: {order.status}"
            }, status=status.HTTP_400_BAD_REQUEST)

        # If vendor, verify they own products in this order
        if is_vendor:
            vendor = request.user.store
            vendor_items = order.order_items.filter(product__store=vendor).count()
            if vendor_items == 0:
                return Response({"message": "Forbidden - Order contains no items from your store"}, status=403)

        try:
            with transaction.atomic():
                # Update order status
                order.status = Order.Status.SHIPPED
                order.shipped_at = timezone.now()
                tracking_number = request.data.get('tracking_number')
                if tracking_number:
                    order.tracking_number = tracking_number
                order.save(update_fields=['status', 'shipped_at', 'tracking_number'] if tracking_number else ['status', 'shipped_at'])
                
                # Create order status history
                OrderStatusHistory.objects.create(
                    order=order,
                    status=Order.Status.SHIPPED,
                    changed_by='ADMIN' if is_admin else 'VENDOR',
                    admin=request.user if is_admin else None,
                    reason=f"Order marked as shipped by {'admin' if is_admin else 'vendor'}"
                )
                
                # Create transaction log
                from transactions.models import TransactionLog
                TransactionLog.objects.create(
                    order=order,
                    action=TransactionLog.Action.ORDER_SHIPPED,
                    level=TransactionLog.Level.SUCCESS,
                    message=f"Order {order.order_id} marked as SHIPPED. Tracking: {tracking_number or 'Not provided'}",
                    related_user=request.user,
                    metadata={
                        "order_id": str(order.order_id),
                        "tracking_number": tracking_number,
                        "marked_by": "admin" if is_admin else "vendor",
                        "marked_by_email": request.user.email
                    }
                )
                
                # Notify customer using WebSocket
                send_order_notification(
                    order.customer,
                    "Your Order is On the Way",
                    f"Order {order.order_id} has been shipped! "
                    f"{f'Tracking number: {tracking_number}' if tracking_number else 'Your delivery agent will contact you soon.'}",
                    order_id=order.order_id
                )
                
                logger.info(
                    f"Order {order.order_id} marked as SHIPPED by {request.user.email} | "
                    f"User type: {'admin' if is_admin else 'vendor'} | "
                    f"Tracking: {tracking_number or 'Not provided'}"
                )
        
        except Exception as e:
            logger.error(f"Error marking order {order.order_id} as shipped: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": f"Error marking order as shipped: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": "Order marked as SHIPPED successfully",
            "order_id": str(order.order_id),
            "status": order.status,
            "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
            "tracking_number": order.tracking_number,
            "marked_by": "admin" if is_admin else "vendor"
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="admin_mark_order_delivered",
        operation_summary="Mark Order as DELIVERED",
        operation_description="""Mark an order as DELIVERED (Step 10 in order flow).
        
Flow Step: 9 → 10
- Admin or Vendor marks as SHIPPED
- Delivery agent or Admin marks as DELIVERED
- Vendors credited for order
- Customer & Admins notified of delivery
- Order completion flow finished
        
This action:
- Updates order status to DELIVERED
- Records timestamp when order was delivered
- Credits all vendors their share (with 10% platform commission deducted)
- Sends notifications to customer, vendors, admins, and delivery agent
- Creates audit trail with OrderStatusHistory
- Creates transaction logs for vendor credits

Access: Delivery Agent (assigned to order) or Admin (staff)""",
        tags=["Orders & Logistics"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_STRING, description='Order UUID'),
                'delivery_notes': openapi.Schema(type=openapi.TYPE_STRING, description='Optional delivery notes'),
            },
            required=['order_id']
        ),
        responses={
            200: openapi.Response("Order marked as delivered successfully"),
            400: openapi.Response("Invalid request or order not in SHIPPED status"),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Delivery Agent or Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def mark_delivered(self, request):
        from users.models import DeliveryAgent
        
        # Check if user is a delivery agent or admin
        delivery_agent = DeliveryAgent.objects.filter(user=request.user).first() if request.user else None
        is_admin = request.user.is_staff if request.user else False
        
        if not delivery_agent and not is_admin:
            return Response({"message": "Access denied - Delivery Agent or Admin only"}, status=403)

        try:
            order = Order.objects.get(order_id=request.data.get('order_id'))
        except Order.DoesNotExist:
            return Response({"success": False, "message": "Order not found"}, status=404)

        # Verify order is in SHIPPED status
        if order.status != Order.Status.SHIPPED:
            return Response({
                "success": False, 
                "message": f"Order must be in SHIPPED status to mark as DELIVERED. Current status: {order.status}"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify delivery agent is assigned (if not admin)
        if delivery_agent and order.delivery_agent != delivery_agent:
            return Response({"message": "Forbidden - You are not assigned to this order"}, status=403)

        try:
            with transaction.atomic():
                # Update order status
                order.status = Order.Status.DELIVERED
                order.delivered_at = timezone.now()
                order.save(update_fields=['status', 'delivered_at'])
                
                # Create order status history
                OrderStatusHistory.objects.create(
                    order=order,
                    status=Order.Status.DELIVERED,
                    changed_by='ADMIN' if is_admin else 'SYSTEM',
                    admin=request.user if is_admin else None,
                    reason=f"Order delivered by {'admin' if is_admin else 'delivery agent'}"
                )
                
                # Credit vendors (only if not already credited)
                if not order.vendors_credited:
                    from transactions.views import credit_vendors_for_order
                    from transactions.models import TransactionLog
                    
                    credit_vendors_for_order(order, source_prefix="Delivery")
                    order.vendors_credited = True
                    order.save(update_fields=['vendors_credited'])
                    
                    logger.info(f"Vendors credited for order {order.order_id}")
                
                # Create transaction log
                from transactions.models import TransactionLog
                TransactionLog.objects.create(
                    order=order,
                    action=TransactionLog.Action.ORDER_DELIVERED,
                    level=TransactionLog.Level.SUCCESS,
                    message=f"Order {order.order_id} marked as DELIVERED. Vendors credited.",
                    related_user=request.user,
                    metadata={
                        "order_id": str(order.order_id),
                        "delivered_by": "admin" if is_admin else "delivery_agent",
                        "delivered_by_email": request.user.email,
                        "delivery_notes": request.data.get('delivery_notes', '')
                    }
                )
                
                # Notify customer
                send_order_notification(
                    order.customer,
                    "Order Delivered Successfully",
                    f"Your order {order.order_id} has been delivered! Thank you for shopping with us.",
                    order_id=order.order_id
                )
                
                # Notify all admins about order completion
                admin_users = CustomUser.objects.filter(is_staff=True).exclude(id=request.user.id)
                for admin in admin_users:
                    notify_admin(
                        "Order Delivered & Fulfilled",
                        f"Order {order.order_id} (₦{order.total_price}) has been delivered successfully. "
                        f"Customer: {order.customer.email}. Vendors have been credited.",
                        order_id=order.order_id,
                        customer_email=order.customer.email
                    )
                
                # Notify vendors
                vendors = {item.product.store for item in order.order_items.all() if item.product.store}
                for vendor in vendors:
                    send_order_notification(
                        vendor,
                        "Order Delivered - Payment Released",
                        f"Order {order.order_id} has been delivered. Earnings have been credited to your wallet.",
                        order_id=order.order_id
                    )
                
                # Notify delivery agent (if applicable) using WebSocket
                if order.delivery_agent:
                    send_delivery_notification(
                        order.delivery_agent.user,
                        "Delivery Completed",
                        f"Order {order.order_id} has been marked as delivered.",
                        order_id=order.order_id
                    )
                
                logger.info(
                    f"Order {order.order_id} marked as DELIVERED by {request.user.email} | "
                    f"User type: {'admin' if is_admin else 'delivery_agent'} | "
                    f"Vendors credited: {not order.vendors_credited}"
                )
        
        except Exception as e:
            logger.error(f"Error marking order {order.order_id} as delivered: {str(e)}", exc_info=True)
            return Response({
                "success": False,
                "message": f"Error marking order as delivered: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "message": "Order marked as DELIVERED successfully",
            "order_id": str(order.order_id),
            "status": order.status,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "vendors_credited": order.vendors_credited,
            "marked_by": "admin" if is_admin else "delivery_agent"
        }, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="admin_process_refund",
        operation_summary="Process Order Refund",
        operation_description="Process a refund for an order and update its status to refunded.",
        tags=["Orders & Logistics"],
        request_body=AdminOrderActionSerializer,
        responses={
            200: openapi.Response(
                "Refund processed successfully",
                AdminOrderActionResponseSerializer()
            ),
            400: openapi.Response("Invalid request data"),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def process_refund(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminOrderActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = Order.objects.filter(uuid=serializer.validated_data["order_uuid"]).first()
        if not order:
            return Response({"success": False, "message": "Order not found"}, status=404)

        order.status = "refunded"
        order.save(update_fields=["status"])

        response_serializer = AdminOrderActionResponseSerializer({"success": True})
        return Response(response_serializer.data)


class AdminFinanceViewSet(AdminBaseViewSet):
    """
    ViewSet for admin financial management including payments and vendor payouts.
    """

    @swagger_auto_schema(
        operation_id="admin_list_payments",
        operation_summary="Get All Payments",
        operation_description="Retrieve all payment records from the platform with customer and amount information.",
        tags=["Finance"],
        responses={
            200: openapi.Response(
                "Payments retrieved successfully",
                AdminFinancePaymentSerializer(many=True)
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def payments(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        payments = Payment.objects.all()
        serializer = AdminFinancePaymentSerializer(payments, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_id="admin_trigger_payout",
        operation_summary="Trigger Vendor/Customer Payout",
        operation_description="Calculate and execute a payout for a vendor or customer based on their available balance.",
        tags=["Finance"],
        request_body=AdminFinancePayoutSerializer,
        responses={
            200: openapi.Response(
                "Payout triggered successfully",
                AdminFinancePayoutResponseSerializer()
            ),
            400: openapi.Response("Invalid user UUID or nothing to payout"),
            404: openapi.Response("User not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def trigger_payout(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminFinancePayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_user_by_uuid(serializer.validated_data["user_uuid"])
        if not user:
            return Response({"message": "User not found"}, status=404)

        total_payable = PayoutService.calculate_payout(user)
        if total_payable <= 0:
            return Response({"message": "Nothing to payout"}, status=400)

        PayoutService.execute_payout(user, total_payable)

        return Response({"success": True, "amount": total_payable})

    @swagger_auto_schema(
        operation_id="admin_list_withdrawals",
        operation_summary="List All Withdrawal Requests",
        operation_description="Retrieve all withdrawal requests from vendors and customers with filtering options.",
        tags=["Finance - Withdrawals"],
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description='Filter by status: pending, processing, successful, failed, cancelled',
                type=openapi.TYPE_STRING,
                required=False,
            ),
            openapi.Parameter(
                'type',
                openapi.IN_QUERY,
                description='Filter by type: vendor, customer, all',
                type=openapi.TYPE_STRING,
                required=False,
            ),
        ],
        responses={
            200: openapi.Response("Withdrawal requests retrieved successfully"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_withdrawals(self, request):
        """List all withdrawal requests with optional filtering"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        from users.models import PayoutRequest
        
        # Get filters
        status_filter = request.query_params.get('status')
        type_filter = request.query_params.get('type', 'all').lower()
        
        # Build query
        withdrawals = PayoutRequest.objects.all()
        
        # Filter by status if provided
        if status_filter:
            withdrawals = withdrawals.filter(status=status_filter.lower())
        
        # Filter by type (vendor or customer)
        if type_filter == 'vendor':
            withdrawals = withdrawals.filter(vendor__isnull=False)
        elif type_filter == 'customer':
            withdrawals = withdrawals.filter(user__isnull=False, vendor__isnull=True)
        
        # Order by created date descending
        withdrawals = withdrawals.order_by('-created_at')
        
        # Serialize
        withdrawal_data = []
        for w in withdrawals:
            if w.vendor:
                requestor_name = w.vendor.store_name
                requestor_email = w.vendor.user.email
                requestor_type = 'Vendor'
            else:
                requestor_name = w.user.full_name or w.user.email
                requestor_email = w.user.email
                requestor_type = 'Customer'
            
            withdrawal_data.append({
                'id': w.id,
                'reference': w.reference,
                'amount': str(w.amount),
                'requestor_name': requestor_name,
                'requestor_email': requestor_email,
                'requestor_type': requestor_type,
                'status': w.status,
                'bank_name': w.bank_name,
                'account_number': w.account_number,
                'account_name': w.account_name,
                'created_at': w.created_at.isoformat(),
                'processed_at': w.processed_at.isoformat() if w.processed_at else None,
                'failure_reason': w.failure_reason,
            })
        
        return Response({
            "success": True,
            "count": len(withdrawal_data),
            "data": withdrawal_data
        })

    @swagger_auto_schema(
        operation_id="admin_withdrawal_detail",
        operation_summary="Get Withdrawal Request Details",
        operation_description="Retrieve detailed information about a specific withdrawal request.",
        tags=["Finance - Withdrawals"],
        responses={
            200: openapi.Response("Withdrawal request details retrieved successfully"),
            404: openapi.Response("Withdrawal request not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def withdrawal_detail(self, request):
        """Get details of a specific withdrawal request"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        withdrawal_id = request.query_params.get('id')
        if not withdrawal_id:
            return Response({"message": "Withdrawal ID is required"}, status=400)
        
        from users.models import PayoutRequest
        try:
            w = PayoutRequest.objects.get(id=withdrawal_id)
        except PayoutRequest.DoesNotExist:
            return Response({"message": "Withdrawal request not found"}, status=404)
        
        if w.vendor:
            requestor_name = w.vendor.store_name
            requestor_email = w.vendor.user.email
            requestor_type = 'Vendor'
            requestor_id = str(w.vendor.user.uuid)
        else:
            requestor_name = w.user.full_name or w.user.email
            requestor_email = w.user.email
            requestor_type = 'Customer'
            requestor_id = str(w.user.uuid)
        
        detail = {
            'id': w.id,
            'reference': w.reference,
            'amount': str(w.amount),
            'requestor_name': requestor_name,
            'requestor_email': requestor_email,
            'requestor_type': requestor_type,
            'requestor_id': requestor_id,
            'status': w.status,
            'bank_name': w.bank_name,
            'account_number': w.account_number,
            'account_name': w.account_name,
            'recipient_code': w.recipient_code,
            'created_at': w.created_at.isoformat(),
            'processed_at': w.processed_at.isoformat() if w.processed_at else None,
            'failure_reason': w.failure_reason,
        }
        
        return Response({"success": True, "data": detail})

    @swagger_auto_schema(
        operation_id="admin_approve_withdrawal",
        operation_summary="Approve Withdrawal Request",
        operation_description="Approve a pending withdrawal request and process the payout.",
        tags=["Finance - Withdrawals"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'withdrawal_id': openapi.Schema(type=openapi.TYPE_STRING, description='Withdrawal request ID'),
                'notes': openapi.Schema(type=openapi.TYPE_STRING, description='Optional approval notes'),
            },
            required=['withdrawal_id']
        ),
        responses={
            200: openapi.Response("Withdrawal approved successfully"),
            400: openapi.Response("Invalid request"),
            404: openapi.Response("Withdrawal request not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def approve_withdrawal(self, request):
        """Approve a withdrawal request"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        withdrawal_id = request.data.get('withdrawal_id')
        if not withdrawal_id:
            return Response({"message": "withdrawal_id is required"}, status=400)
        
        from users.models import PayoutRequest
        from django.utils import timezone
        
        try:
            w = PayoutRequest.objects.get(id=withdrawal_id)
        except PayoutRequest.DoesNotExist:
            return Response({"message": "Withdrawal request not found"}, status=404)
        
        if w.status != 'pending':
            return Response(
                {"message": f"Cannot approve withdrawal with status '{w.status}'"},
                status=400
            )
        
        try:
            # Update status to processing
            w.status = 'processing'
            w.processed_at = timezone.now()
            w.save()
            
            # TODO: Integrate with payment provider (Paystack, etc.) to process actual transfer
            # For now, we'll mark as successful
            # In production, this should be done via a task queue (Celery)
            
            # Notify the requestor
            from users.notification_service import NotificationService
            if w.vendor:
                user = w.vendor.user
                requestor_name = w.vendor.store_name
                requestor_type = "Vendor"
            else:
                user = w.user
                requestor_name = user.full_name or user.email
                requestor_type = "Customer"
            
            NotificationService.create_notification(
                user=user,
                title="Withdrawal Approved",
                message=f"Your withdrawal request of ₦{w.amount:,.2f} has been approved and is being processed.",
                category='withdrawal',
                priority='high',
                description=f"Your withdrawal to {w.account_name} ({w.account_number}) is now being processed. Reference: {w.reference}",
                action_url=f"/wallet/withdrawals/{w.id}",
                action_text="View Status",
                metadata={
                    'withdrawal_id': str(w.id),
                    'reference': w.reference,
                    'amount': str(w.amount),
                },
                send_websocket=True,
                send_email=True,
            )
            
            return Response({
                "success": True,
                "message": f"Withdrawal {w.reference} approved and marked for processing"
            })
        except Exception as e:
            logger.error(f"Error approving withdrawal {withdrawal_id}: {str(e)}", exc_info=True)
            return Response(
                {"message": f"Error approving withdrawal: {str(e)}"},
                status=400
            )

    @swagger_auto_schema(
        operation_id="admin_reject_withdrawal",
        operation_summary="Reject Withdrawal Request",
        operation_description="Reject a pending withdrawal request and refund the amount to wallet.",
        tags=["Finance - Withdrawals"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'withdrawal_id': openapi.Schema(type=openapi.TYPE_STRING, description='Withdrawal request ID'),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description='Reason for rejection'),
            },
            required=['withdrawal_id', 'reason']
        ),
        responses={
            200: openapi.Response("Withdrawal rejected successfully"),
            400: openapi.Response("Invalid request"),
            404: openapi.Response("Withdrawal request not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def reject_withdrawal(self, request):
        """Reject a withdrawal request and refund to wallet"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        withdrawal_id = request.data.get('withdrawal_id')
        reason = request.data.get('reason', '')
        
        if not withdrawal_id:
            return Response({"message": "withdrawal_id is required"}, status=400)
        
        from users.models import PayoutRequest
        from transactions.models import Wallet
        from django.utils import timezone
        
        try:
            w = PayoutRequest.objects.get(id=withdrawal_id)
        except PayoutRequest.DoesNotExist:
            return Response({"message": "Withdrawal request not found"}, status=404)
        
        if w.status != 'pending':
            return Response(
                {"message": f"Cannot reject withdrawal with status '{w.status}'"},
                status=400
            )
        
        try:
            # Refund to wallet
            if w.vendor:
                wallet = w.vendor.user.wallet
            else:
                wallet = w.user.wallet
            
            wallet.credit(w.amount, source=f"Withdrawal Refund {w.reference}")
            
            # Update withdrawal status
            w.status = 'failed'
            w.failure_reason = reason
            w.processed_at = timezone.now()
            w.save()
            
            # Notify the requestor
            from users.notification_service import NotificationService
            if w.vendor:
                user = w.vendor.user
                requestor_name = w.vendor.store_name
            else:
                user = w.user
                requestor_name = user.full_name or user.email
            
            NotificationService.create_notification(
                user=user,
                title="Withdrawal Rejected",
                message=f"Your withdrawal request of ₦{w.amount:,.2f} has been rejected.",
                category='withdrawal',
                priority='high',
                description=f"Reason: {reason}\n\nThe amount has been refunded to your wallet. Reference: {w.reference}",
                action_url=f"/wallet",
                action_text="View Wallet",
                metadata={
                    'withdrawal_id': str(w.id),
                    'reference': w.reference,
                    'amount': str(w.amount),
                    'reason': reason,
                },
                send_websocket=True,
                send_email=True,
            )
            
            return Response({
                "success": True,
                "message": f"Withdrawal {w.reference} rejected. Amount of ₦{w.amount:,.2f} refunded to wallet."
            })
        except Exception as e:
            logger.error(f"Error rejecting withdrawal {withdrawal_id}: {str(e)}", exc_info=True)
            return Response(
                {"message": f"Error rejecting withdrawal: {str(e)}"},
                status=400
            )


class AdminAnalyticsViewSet(AdminBaseViewSet):
    """
    ViewSet for admin analytics and reporting on platform performance.
    """

    @swagger_auto_schema(
        operation_id="admin_analytics_overview",
        operation_summary="Admin Analytics Overview",
        operation_description="Get platform-wide analytics including total users, vendors, orders, and products.",
        tags=["Analytics"],
        responses={
            200: openapi.Response(
                "Analytics data retrieved successfully",
                AdminAnalyticsSerializer()
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def overview(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        from authentication.models import CustomUser
        from users.models import Vendor
        from decimal import Decimal
        
        # Count total vendors
        total_vendors = Vendor.objects.count()
        
        # Count total orders
        total_orders = Order.objects.count()
        
        # Count pending orders (not delivered or canceled)
        pending_orders = Order.objects.exclude(
            status__in=[Order.Status.DELIVERED, Order.Status.CANCELED, Order.Status.RETURNED]
        ).count()
        
        # Calculate total revenue from delivered and paid orders
        delivered_paid_orders = Order.objects.filter(
            status=Order.Status.DELIVERED,
            payment_status='PAID'
        )
        total_revenue = Decimal('0.00')
        for order in delivered_paid_orders:
            total_revenue += order.total_price
        
        data = {
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "total_vendors": total_vendors,
        }

        serializer = AdminAnalyticsSerializer(data)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_id="admin_analytics_detailed",
        operation_summary="Admin Detailed Analytics",
        operation_description="Get detailed admin analytics including sales chart data and order status breakdown.",
        tags=["Analytics"],
        manual_parameters=[
            openapi.Parameter(
                'sales_period',
                openapi.IN_QUERY,
                description='Sales period: daily, weekly, or annually (default: annually)',
                type=openapi.TYPE_STRING,
                required=False,
            )
        ],
        responses={
            200: openapi.Response(
                "Detailed analytics data retrieved successfully",
                AdminDetailedAnalyticsSerializer()
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"], url_path="detailed")
    def detailed(self, request):
        """Get detailed analytics with sales chart and order status breakdown"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        from authentication.models import CustomUser
        from users.models import Vendor
        from decimal import Decimal
        from django.db.models import Sum, Q
        from django.utils import timezone
        from datetime import timedelta
        
        sales_period = request.query_params.get('sales_period', 'annually')
        
        # Get total counts
        total_users = CustomUser.objects.filter(role='CUSTOMER').count()
        total_vendors = Vendor.objects.count()
        total_orders = Order.objects.count()
        
        # Calculate total sales from delivered and paid orders
        delivered_paid_orders = Order.objects.filter(
            status=Order.Status.DELIVERED,
            payment_status='PAID'
        )
        total_sales = Decimal('0.00')
        for order in delivered_paid_orders:
            total_sales += order.total_price
        
        # Generate sales chart data based on sales_period
        sales_chart_data = self._generate_sales_chart(sales_period)
        
        # Get order status breakdown
        order_stats = {
            "completed": Order.objects.filter(status=Order.Status.DELIVERED).count(),
            "pending": Order.objects.exclude(
                status__in=[Order.Status.DELIVERED, Order.Status.CANCELED, Order.Status.RETURNED]
            ).count(),
            "cancelled": Order.objects.filter(status=Order.Status.CANCELED).count(),
            "returned": Order.objects.filter(status=Order.Status.RETURNED).count(),
        }
        
        data = {
            "total_sales": total_sales,
            "total_vendors": total_vendors,
            "total_orders": total_orders,
            "total_users": total_users,
            "sales_chart_data": sales_chart_data,
            "order_stats": order_stats,
        }
        
        serializer = AdminDetailedAnalyticsSerializer(data)
        return Response({"success": True, "data": serializer.data})

    def _generate_sales_chart(self, period):
        """Generate sales chart data based on the specified period"""
        from decimal import Decimal
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Sum
        
        now = timezone.now()
        chart_data = []
        
        if period == 'daily':
            # Last 7 days
            for i in range(6, -1, -1):
                day = now - timedelta(days=i)
                start_of_day = day.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = day.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                sales = Order.objects.filter(
                    status=Order.Status.DELIVERED,
                    payment_status='PAID',
                    delivered_at__range=[start_of_day, end_of_day]
                ).aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0.00')
                
                chart_data.append({
                    "period": day.strftime('%Y-%m-%d'),
                    "sales": sales
                })
        
        elif period == 'weekly':
            # Last 12 weeks
            for i in range(11, -1, -1):
                week_start = now - timedelta(weeks=i+1)
                week_end = week_start + timedelta(weeks=1)
                
                sales = Order.objects.filter(
                    status=Order.Status.DELIVERED,
                    payment_status='PAID',
                    delivered_at__range=[week_start, week_end]
                ).aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0.00')
                
                # Format as "Week 1" or date range
                chart_data.append({
                    "period": f"Week of {week_start.strftime('%Y-%m-%d')}",
                    "sales": sales
                })
        
        else:  # annually (default)
            # Last 3 years
            for i in range(2, -1, -1):
                year = now.year - i
                year_start = timezone.make_aware(timezone.datetime(year, 1, 1))
                year_end = timezone.make_aware(timezone.datetime(year, 12, 31, 23, 59, 59))
                
                sales = Order.objects.filter(
                    status=Order.Status.DELIVERED,
                    payment_status='PAID',
                    delivered_at__range=[year_start, year_end]
                ).aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0.00')
                
                chart_data.append({
                    "period": str(year),
                    "sales": sales
                })
        
        return chart_data


# =====================================================
# DELIVERY AGENT VIEWSET
# =====================================================
class DeliveryAgentViewSet(viewsets.ViewSet):
    """
    ViewSet for delivery agents to manage their profile and assigned orders.
    
    Endpoints:
    - GET /api/delivery/profile/: Retrieve delivery agent profile
    - PATCH /api/delivery/profile/: Update delivery agent profile
    - GET /api/delivery/assigned-orders/: List assigned orders
    - PATCH /api/delivery/mark-delivered/:order_id/: Mark order as delivered
    - GET /api/delivery/stats/: Get delivery agent statistics
    """
    permission_classes = [IsAuthenticated]

    def get_delivery_agent(self, request):
        """Get delivery agent or return None"""
        try:
            return request.user.deliveryagent
        except:
            return None

    @swagger_auto_schema(
        operation_id="delivery_profile_retrieve",
        operation_summary="Get Delivery Agent Profile",
        operation_description="Retrieve the authenticated delivery agent's profile information.",
        tags=["Delivery Agent"],
        responses={
            200: openapi.Response("Profile retrieved successfully", DeliveryAgentProfileSerializer()),
            403: openapi.Response("Delivery agent access only"),
        },
        security=[{"Bearer": []}],
    )
    def list(self, request):
        """Get delivery agent profile"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = DeliveryAgentProfileSerializer(agent)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="delivery_profile_update",
        operation_summary="Update Delivery Agent Profile",
        operation_description="Partially update delivery agent profile (phone, is_active).",
        tags=["Delivery Agent"],
        request_body=DeliveryAgentUpdateSerializer,
        responses={
            200: openapi.Response("Profile updated successfully", DeliveryAgentProfileSerializer()),
            400: openapi.Response("Invalid input data"),
            403: openapi.Response("Delivery agent access only"),
        },
        security=[{"Bearer": []}],
    )
    def partial_update(self, request):
        """Update delivery agent profile"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = DeliveryAgentUpdateSerializer(agent, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            response_serializer = DeliveryAgentProfileSerializer(agent)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_id="delivery_assigned_orders",
        operation_summary="List Assigned Orders",
        operation_description="Get list of orders assigned to the delivery agent.",
        tags=["Delivery Agent"],
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description='Filter by order status: PENDING, SHIPPED, DELIVERED',
                type=openapi.TYPE_STRING,
            )
        ],
        responses={
            200: openapi.Response("Orders retrieved successfully"),
            403: openapi.Response("Delivery agent access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['get'])
    def assigned_orders(self, request):
        """Get assigned orders for delivery agent"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        orders = Order.objects.filter(delivery_agent=agent).order_by('-assigned_at')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            orders = orders.filter(status=status_filter)
        
        from transactions.serializers import OrderSerializer
        serializer = OrderSerializer(orders, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="delivery_mark_delivered",
        operation_summary="Mark Order as Delivered",
        operation_description="Update order status to DELIVERED and notify customer.",
        tags=["Delivery Agent"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'notes': openapi.Schema(type=openapi.TYPE_STRING, description='Delivery notes (optional)')
            }
        ),
        responses={
            200: openapi.Response("Order marked as delivered"),
            400: openapi.Response("Invalid order or already delivered"),
            403: openapi.Response("Not authorized to update this order"),
            404: openapi.Response("Order not found"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['patch'], url_path='mark-delivered/(?P<order_id>[^/.]+)')
    def mark_delivered(self, request, order_id=None):
        """Mark order as delivered"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        try:
            order = Order.objects.get(order_id=order_id, delivery_agent=agent)
        except Order.DoesNotExist:
            return Response(
                {"detail": "Order not found or not assigned to you"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        if order.status == Order.Status.DELIVERED:
            return Response(
                {"detail": "Order already marked as delivered"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Mark order as delivered
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at', 'updated_at'])
        
        # Credit vendors for delivered order (only if not already credited)
        if not order.vendors_credited:
            from transactions.views import credit_vendors_for_order
            try:
                credit_vendors_for_order(order)
                order.vendors_credited = True
                order.save(update_fields=['vendors_credited'])
            except Exception as e:
                logger.error(f"Failed to credit vendors for delivered order {order.order_id}: {e}")
        
        # Create notification for customer
        send_order_notification(
            order.customer,
            "Order Delivered",
            f"Your order {order.order_id} has been delivered.",
            order_id=order.order_id
        )
        
        from transactions.serializers import OrderSerializer
        serializer = OrderSerializer(order, context={'request': request})
        return Response(
            {"success": True, "message": "Order marked as delivered", "order": serializer.data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="delivery_stats",
        operation_summary="Get Delivery Agent Statistics",
        operation_description="Get statistics for the delivery agent including total assignments, deliveries, and success rate.",
        tags=["Delivery Agent"],
        responses={
            200: openapi.Response("Statistics retrieved successfully", DeliveryAgentStatsSerializer()),
            403: openapi.Response("Delivery agent access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get delivery agent statistics"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        orders = agent.assigned_orders.all()
        total_assigned = orders.count()
        total_delivered = orders.filter(status=Order.Status.DELIVERED).count()
        pending_deliveries = orders.exclude(status=Order.Status.DELIVERED).count()
        
        success_rate = (total_delivered / total_assigned * 100) if total_assigned > 0 else 0
        
        data = {
            'total_assigned': total_assigned,
            'total_delivered': total_delivered,
            'pending_deliveries': pending_deliveries,
            'delivery_success_rate': round(success_rate, 2),
        }
        
        serializer = DeliveryAgentStatsSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="delivery_notifications",
        operation_summary="Get Delivery Agent Notifications",
        operation_description="Get notifications for the delivery agent including new assignments and updates.",
        tags=["Delivery Agent"],
        responses={
            200: openapi.Response("Notifications retrieved successfully"),
            403: openapi.Response("Delivery agent access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['get'])
    def notifications(self, request):
        """Get delivery agent notifications"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        notifications = Notification.objects.filter(user=agent.user).order_by('-created_at')[:50]
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="delivery_pending_deliveries",
        operation_summary="Get Pending Deliveries",
        operation_description="Get list of orders assigned to delivery agent that are not yet delivered.",
        tags=["Delivery Agent"],
        responses={
            200: openapi.Response("Pending deliveries retrieved successfully"),
            403: openapi.Response("Delivery agent access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['get'])
    def pending_deliveries(self, request):
        """Get pending deliveries for delivery agent"""
        agent = self.get_delivery_agent(request)
        if not agent:
            return Response(
                {"detail": "Delivery agent access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        pending_orders = agent.assigned_orders.exclude(status=Order.Status.DELIVERED).order_by('assigned_at')
        
        from transactions.serializers import OrderSerializer
        serializer = OrderSerializer(pending_orders, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# =====================================================
# ADMIN DELIVERY AGENT MANAGEMENT
# =====================================================
class AdminDeliveryAgentViewSet(AdminBaseViewSet):
    """
    ViewSet for business admins to manage delivery agents.
    
    Endpoints:
    - GET /api/admin/delivery-agents/: List all delivery agents
    - POST /api/admin/delivery-agents/: Create new delivery agent
    - PATCH /api/admin/delivery-agents/:id/: Update delivery agent status
    - DELETE /api/admin/delivery-agents/:id/: Deactivate delivery agent
    """

    @swagger_auto_schema(
        operation_id="admin_list_delivery_agents",
        operation_summary="List All Delivery Agents",
        operation_description="Get list of all delivery agents with their statistics.",
        tags=["Admin - Delivery Agents"],
        responses={
            200: openapi.Response("Delivery agents retrieved successfully"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['get'])
    def list_agents(self, request):
        """List all delivery agents"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        from users.models import DeliveryAgent
        agents = DeliveryAgent.objects.all().order_by('created_at')
        serializer = DeliveryAgentListSerializer(agents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_id="admin_create_delivery_agent",
        operation_summary="Create New Delivery Agent",
        operation_description="Create a new delivery agent account (rider).",
        tags=["Admin - Delivery Agents"],
        request_body=DeliveryAgentCreateSerializer,
        responses={
            201: openapi.Response("Delivery agent created successfully"),
            400: openapi.Response("Invalid input data"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['post'])
    def create_agent(self, request):
        """Create a new delivery agent"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = DeliveryAgentCreateSerializer(data=request.data)
        if serializer.is_valid():
            agent = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Delivery agent created successfully",
                    "agent_id": agent.id,
                    "email": agent.user.email,
                    "full_name": agent.user.full_name,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_id="admin_deactivate_delivery_agent",
        operation_summary="Deactivate Delivery Agent",
        operation_description="Deactivate a delivery agent (remove from active rotation).",
        tags=["Admin - Delivery Agents"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'agent_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Delivery Agent ID'),
                'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN, description='Active status')
            },
            required=['agent_id']
        ),
        responses={
            200: openapi.Response("Delivery agent status updated"),
            404: openapi.Response("Delivery agent not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['patch'])
    def update_agent_status(self, request):
        """Update delivery agent status"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        agent_id = request.data.get('agent_id')
        is_active = request.data.get('is_active', False)

        if not agent_id:
            return Response({"message": "agent_id is required"}, status=400)

        from users.models import DeliveryAgent
        try:
            agent = DeliveryAgent.objects.get(id=agent_id)
        except DeliveryAgent.DoesNotExist:
            return Response({"message": "Delivery agent not found"}, status=404)

        agent.is_active = is_active
        agent.save(update_fields=['is_active'])

        status_text = "activated" if is_active else "deactivated"
        return Response(
            {
                "success": True,
                "message": f"Delivery agent {status_text}",
                "agent_id": agent.id,
                "is_active": agent.is_active,
            },
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="admin_get_agent_details",
        operation_summary="Get Delivery Agent Details",
        operation_description="Get detailed information about a specific delivery agent including performance metrics.",
        tags=["Admin - Delivery Agents"],
        responses={
            200: openapi.Response("Agent details retrieved successfully"),
            404: openapi.Response("Delivery agent not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=['get'], url_path='details/(?P<agent_id>[^/.]+)')
    def get_agent_details(self, request, agent_id=None):
        """Get detailed information about a delivery agent"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        from users.models import DeliveryAgent
        try:
            agent = DeliveryAgent.objects.get(id=agent_id)
        except DeliveryAgent.DoesNotExist:
            return Response({"message": "Delivery agent not found"}, status=404)

        orders = agent.assigned_orders.all()
        total_assigned = orders.count()
        total_delivered = orders.filter(status=Order.Status.DELIVERED).count()
        pending = orders.exclude(status=Order.Status.DELIVERED).count()
        success_rate = (total_delivered / total_assigned * 100) if total_assigned > 0 else 0

        data = {
            "id": agent.id,
            "email": agent.user.email,
            "full_name": agent.user.full_name,
            "phone": agent.phone,
            "is_active": agent.is_active,
            "created_at": agent.created_at,
            "total_assigned": total_assigned,
            "total_delivered": total_delivered,
            "pending_deliveries": pending,
            "success_rate": round(success_rate, 2),
        }

        return Response(data, status=status.HTTP_200_OK)


# ---------------------------
# Notifications
# ---------------------------
from rest_framework import generics
from rest_framework.decorators import action as action_decorator
from rest_framework.response import Response as DRFResponse
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT
from drf_spectacular.utils import extend_schema, OpenApiParameter
from authentication.core.base_view import BaseAPIView
from authentication.core.response import standardized_response


class NotificationsListView(BaseAPIView, generics.ListAPIView):
    """
    Get all notifications for the authenticated user.
    Sorted by most recent first.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        """Get notifications for current user, ordered by most recent"""
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    @extend_schema(
        tags=["Notifications"],
        description="Get all notifications for the authenticated user",
        parameters=[
            OpenApiParameter(
                name='is_read',
                description='Filter by read status (true/false)',
                required=False,
                type=bool
            ),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Filter by read status if provided
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            is_read = is_read.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(is_read=is_read)
        
        serializer = self.get_serializer(queryset, many=True)
        return DRFResponse(
            standardized_response(
                data=serializer.data,
                message=f"Retrieved {len(serializer.data)} notifications"
            )
        )


class NotificationDetailView(BaseAPIView):
    """
    Get, mark as read, or delete a specific notification.
    """
    permission_classes = [IsAuthenticated]

    def get_notification(self, notification_id):
        """Get notification and ensure user owns it"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=self.request.user
            )
            return notification
        except Notification.DoesNotExist:
            return None

    @extend_schema(
        tags=["Notifications"],
        description="Get a specific notification",
        responses={
            200: NotificationSerializer,
            404: {"description": "Notification not found"},
        },
    )
    def get(self, request, notification_id):
        """Get a specific notification"""
        notification = self.get_notification(notification_id)
        if not notification:
            return DRFResponse(
                standardized_response(success=False, error="Notification not found"),
                status=404
            )
        
        serializer = NotificationSerializer(notification)
        return DRFResponse(standardized_response(data=serializer.data))

    @extend_schema(
        tags=["Notifications"],
        description="Mark a notification as read",
        responses={
            200: {"description": "Notification marked as read"},
            404: {"description": "Notification not found"},
        },
    )
    def post(self, request, notification_id):
        """Mark notification as read"""
        notification = self.get_notification(notification_id)
        if not notification:
            return DRFResponse(
                standardized_response(success=False, error="Notification not found"),
                status=404
            )
        
        notification.is_read = True
        notification.save()
        
        serializer = NotificationSerializer(notification)
        return DRFResponse(
            standardized_response(
                data=serializer.data,
                message="Notification marked as read"
            )
        )

    @extend_schema(
        tags=["Notifications"],
        description="Delete a notification",
        responses={
            204: {"description": "Notification deleted"},
            404: {"description": "Notification not found"},
        },
    )
    def delete(self, request, notification_id):
        """Delete a notification"""
        notification = self.get_notification(notification_id)
        if not notification:
            return DRFResponse(
                standardized_response(success=False, error="Notification not found"),
                status=404
            )
        
        notification.delete()
        return DRFResponse(
            standardized_response(message="Notification deleted"),
            status=HTTP_204_NO_CONTENT
        )


class UnreadNotificationsCountView(BaseAPIView):
    """
    Get count of unread notifications for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        description="Get count of unread notifications",
        responses={
            200: {
                "description": "Unread count",
                "content": {
                    "application/json": {
                        "example": {
                            "success": True,
                            "data": {"unread_count": 5},
                            "message": "Retrieved unread count"
                        }
                    }
                }
            }
        },
    )
    def get(self, request):
        """Get count of unread notifications"""
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        
        return DRFResponse(
            standardized_response(
                data={"unread_count": unread_count},
                message="Retrieved unread count"
            )
        )


class MarkAllNotificationsReadView(BaseAPIView):
    """
    Mark all unread notifications as read for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        description="Mark all unread notifications as read",
        responses={
            200: {
                "description": "All notifications marked as read",
                "content": {
                    "application/json": {
                        "example": {
                            "success": True,
                            "data": {"marked_as_read": 5},
                            "message": "5 notifications marked as read"
                        }
                    }
                }
            }
        },
    )
    def post(self, request):
        """Mark all notifications as read"""
        unread_notifications = Notification.objects.filter(
            user=request.user,
            is_read=False
        )
        
        count = unread_notifications.count()
        unread_notifications.update(is_read=True)
        
        return DRFResponse(
            standardized_response(
                data={"marked_as_read": count},
                message=f"{count} notifications marked as read"
            )
        )


# =====================================================
# ADMIN NOTIFICATIONS
# =====================================================
class AdminNotificationViewSet(AdminBaseViewSet):
    """
    ViewSet for managing admin notifications (broadcast notifications).
    Allows admins to send, draft, or schedule notifications to users and vendors.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="admin_create_notification",
        operation_summary="Create Admin Notification",
        operation_description="Create a notification for a specific user with priority and category.",
        tags=["Admin Notifications"],
        request_body=AdminNotificationCreateSerializer,
        responses={
            201: openapi.Response(
                "Notification created successfully",
                AdminNotificationCreateSerializer()
            ),
            400: openapi.Response("Invalid data or validation error"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    def create(self, request):
        """Create a notification for a user"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminNotificationCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        notification = serializer.save()

        return Response({
            "success": True,
            "data": AdminNotificationCreateSerializer(notification).data,
            "message": "Notification created successfully"
        }, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        operation_id="admin_list_notifications",
        operation_summary="List Admin Notifications",
        operation_description="Retrieve all admin notifications.",
        tags=["Admin Notifications"],
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description="Filter by notification category",
                type=openapi.TYPE_STRING
            ),
        ],
        responses={
            200: openapi.Response(
                "Notifications retrieved successfully",
                AdminNotificationListSerializer(many=True)
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_notifications(self, request):
        """List all notifications"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        # Get all notifications
        notifications = Notification.objects.all().select_related('user').order_by('-created_at')

        # Filter by category if provided
        category_filter = request.query_params.get('category')
        if category_filter:
            notifications = notifications.filter(category=category_filter)

        serializer = AdminNotificationListSerializer(notifications, many=True)

        return Response({
            "success": True,
            "data": serializer.data,
            "count": notifications.count()
        })


# =====================================================
# ADMIN WALLET & PAYMENTS
# =====================================================
class AdminWalletViewSet(AdminBaseViewSet):
    """
    ViewSet for managing admin wallet, earnings, and withdrawals.
    Mirrors vendor wallet functionality for admin earnings.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="admin_wallet_balance",
        operation_summary="Get Admin Wallet Balance",
        operation_description="Retrieve admin's current wallet balance and earnings summary.",
        tags=["Admin Wallet"],
        responses={
            200: openapi.Response(
                "Wallet balance retrieved successfully",
                AdminWalletBalanceSerializer()
            ),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def balance(self, request):
        """Get admin wallet balance and earnings summary"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Wallet, WalletTransaction
        from django.db.models import Sum
        from django.utils import timezone
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        
        # Total earnings and withdrawals
        total_credits = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='CREDIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        total_debits = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='DEBIT'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # This month earnings
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_earnings = WalletTransaction.objects.filter(
            wallet=wallet,
            transaction_type='CREDIT',
            created_at__gte=month_start
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Count total withdrawals
        from users.models import PayoutRequest
        total_withdrawals = PayoutRequest.objects.filter(
            user=request.user,
            status='successful'
        ).count()
        
        data = {
            'withdrawable_balance': str(wallet.balance),
            'available_balance': str(wallet.balance),
            'total_earnings': str(total_credits),
            'total_withdrawals': total_withdrawals,
            'this_month_earnings': str(this_month_earnings),
        }
        
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="admin_wallet_transactions",
        operation_summary="Get Wallet Transaction History",
        operation_description="Retrieve admin's wallet transaction history.",
        tags=["Admin Wallet"],
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=20),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=0),
        ],
        responses={
            200: openapi.Response("Transactions retrieved successfully"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def transactions(self, request):
        """Get wallet transaction history"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Wallet, WalletTransaction
        from rest_framework.pagination import LimitOffsetPagination
        
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
        
        paginator = LimitOffsetPagination()
        paginated_txns = paginator.paginate_queryset(transactions, request)
        
        data = []
        for txn in paginated_txns:
            data.append({
                'id': f"txn_{txn.id:06d}",
                'type': txn.transaction_type,
                'amount': str(txn.amount),
                'description': txn.source or f"{txn.transaction_type.lower()}",
                'status': 'SUCCESSFUL',
                'created_at': txn.created_at.isoformat()
            })
        
        return paginator.get_paginated_response(data)

    @swagger_auto_schema(
        operation_id="admin_request_withdrawal",
        operation_summary="Request Withdrawal",
        operation_description="Initiate a withdrawal request from admin wallet to configured bank account.",
        tags=["Admin Wallet"],
        request_body=AdminWithdrawalSerializer,
        responses={
            200: openapi.Response("Withdrawal request initiated successfully"),
            400: openapi.Response("Invalid request"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request):
        """Request a withdrawal"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = AdminWithdrawalSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify PIN
        from users.models import PaymentPIN
        try:
            pin_obj = PaymentPIN.objects.get(user=request.user)
            if not pin_obj.verify_pin(serializer.validated_data['pin']):
                return Response(
                    {"success": False, "message": "Invalid PIN"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except PaymentPIN.DoesNotExist:
            return Response(
                {"success": False, "message": "Payment PIN not set. Please set your PIN first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Check balance
        from transactions.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        amount = serializer.validated_data['amount']
        
        if wallet.balance < amount:
            return Response(
                {"success": False, "message": "Insufficient balance"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Get admin payout settings
        from users.models import AdminPayoutProfile
        try:
            payout_profile = AdminPayoutProfile.objects.get(user=request.user)
            if not payout_profile.bank_name or not payout_profile.account_number:
                return Response(
                    {"success": False, "message": "Bank details not configured"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except AdminPayoutProfile.DoesNotExist:
            return Response(
                {"success": False, "message": "Bank details not configured"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Create withdrawal request
        from users.models import PayoutRequest
        import uuid as uuid_lib
        
        payout = PayoutRequest.objects.create(
            user=request.user,
            amount=amount,
            bank_name=payout_profile.bank_name,
            account_number=payout_profile.account_number,
            account_name=payout_profile.account_name or '',
            recipient_code=payout_profile.recipient_code or '',
            reference=f"ADM-{uuid_lib.uuid4().hex[:12].upper()}",
        )
        
        # Debit wallet
        wallet.debit(amount, source=f"Withdrawal {payout.reference}")
        
        message = f"Withdrawal request of ₦{amount:,.2f} initiated successfully."
        return Response(
            {"success": True, "message": message},
            status=status.HTTP_200_OK,
        )


class AdminPaymentSettingsViewSet(AdminBaseViewSet):
    """
    ViewSet for managing admin payment settings and PIN.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="admin_payment_settings_get",
        operation_summary="Get Payment Settings",
        operation_description="Retrieve admin's payment settings and bank account details.",
        tags=["Admin Payment Settings"],
        responses={
            200: openapi.Response("Payment settings retrieved"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def retrieve_settings(self, request):
        """Get payment settings"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from users.models import AdminPayoutProfile
        try:
            profile = AdminPayoutProfile.objects.get(user=request.user)
            data = {
                'bank_name': profile.bank_name or '',
                'account_number': profile.account_number or '',
                'account_name': profile.account_name or '',
            }
        except AdminPayoutProfile.DoesNotExist:
            data = {
                'bank_name': '',
                'account_number': '',
                'account_name': '',
            }
        
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="admin_payment_settings_update",
        operation_summary="Update Payment Settings",
        operation_description="Update admin's bank account details.",
        tags=["Admin Payment Settings"],
        request_body=AdminPaymentSettingsSerializer,
        responses={
            200: openapi.Response("Settings updated successfully"),
            400: openapi.Response("Invalid data"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["put"])
    def update_settings(self, request):
        """Update payment settings"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = AdminPaymentSettingsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        from users.models import AdminPayoutProfile
        profile, created = AdminPayoutProfile.objects.get_or_create(user=request.user)
        
        # Update fields
        if 'bank_name' in serializer.validated_data:
            profile.bank_name = serializer.validated_data['bank_name']
        if 'account_number' in serializer.validated_data:
            profile.account_number = serializer.validated_data['account_number']
        if 'account_name' in serializer.validated_data:
            profile.account_name = serializer.validated_data['account_name']
        
        profile.save()
        
        return Response(
            {"success": True, "message": "Payment settings updated successfully"},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="admin_set_payment_pin",
        operation_summary="Set/Change Payment PIN",
        operation_description="Set or change the 4-digit payment PIN for withdrawals.",
        tags=["Admin Payment Settings"],
        request_body=PaymentPINSerializer,
        responses={
            200: openapi.Response("PIN set successfully"),
            400: openapi.Response("Invalid PIN"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def set_pin(self, request):
        """Set or change payment PIN"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = AdminPaymentPINSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        from users.models import PaymentPIN
        
        # If changing PIN, verify current PIN
        if serializer.validated_data.get('current_pin'):
            try:
                pin_obj = PaymentPIN.objects.get(user=request.user)
                # Verify current PIN (uses check_password internally)
                if not pin_obj.verify_pin(serializer.validated_data['current_pin']):
                    return Response(
                        {"success": False, "message": "Current PIN is incorrect"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except PaymentPIN.DoesNotExist:
                return Response(
                    {"success": False, "message": "Payment PIN not set yet. Omit current_pin for initial setup."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
        # Create or get existing PIN object
        try:
            pin_obj = PaymentPIN.objects.get(user=request.user)
            created = False
        except PaymentPIN.DoesNotExist:
            pin_obj = PaymentPIN()
            pin_obj.user = request.user
            created = True
        
        # Hash and set the new PIN (automatically marks as non-default if not 0000)
        pin_obj.set_pin(serializer.validated_data['new_pin'])
        
        message = "Payment PIN set successfully" if created else "Payment PIN changed successfully"
        return Response(
            {"success": True, "message": message},
            status=status.HTTP_200_OK,
        )


# =====================================================
# ADMIN SETTLEMENTS & DISPUTES
# =====================================================
class AdminSettlementsViewSet(AdminBaseViewSet):
    """
    ViewSet for managing vendor settlements and customer dispute resolution.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="admin_settlements_summary",
        operation_summary="Settlements Summary",
        operation_description="Retrieve platform-level settlement summary statistics.",
        tags=["Admin Settlements"],
        responses={
            200: openapi.Response("Settlements summary retrieved"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get settlements summary"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Settlement, Order, OrderItem
        from django.db.models import Sum, Count
        from django.utils import timezone
        from decimal import Decimal
        
        # Total revenue (GMV) - sum of all order totals
        total_revenue = Order.objects.filter(
            payment_status='PAID'
        ).aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0.00')
        
        # Total payouts - sum of processed settlements
        total_payouts = Settlement.objects.filter(
            status='PROCESSED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        # Pending settlements - sum of pending settlement amounts
        pending_settlements = Settlement.objects.filter(
            status__in=['PENDING', 'PROCESSING']
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        # Upcoming payouts - count of pending settlements
        upcoming_payouts = Settlement.objects.filter(
            status='PENDING',
            payout_date__gt=timezone.now()
        ).values('vendor').distinct().count()
        
        data = {
            'total_revenue': str(total_revenue),
            'total_payouts': str(total_payouts),
            'pending_settlements': str(pending_settlements),
            'upcoming_payouts': upcoming_payouts,
        }
        
        return Response(
            {"success": True, "data": data},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(
        operation_id="admin_vendor_settlements_list",
        operation_summary="Vendor Settlements List",
        operation_description="Retrieve vendor settlement records with filtering.",
        tags=["Admin Settlements"],
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description='Filter by status: PENDING, PROCESSED, FAILED'
            ),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=20),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=0),
        ],
        responses={
            200: openapi.Response("Vendor settlements retrieved"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def vendor(self, request):
        """Get vendor settlements list"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Settlement
        from rest_framework.pagination import LimitOffsetPagination
        
        settlements = Settlement.objects.select_related('vendor').order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter and status_filter.upper() in ['PENDING', 'PROCESSED', 'FAILED']:
            settlements = settlements.filter(status=status_filter.upper())
        
        # Paginate
        paginator = LimitOffsetPagination()
        paginated = paginator.paginate_queryset(settlements, request)
        
        data = []
        for settlement in paginated:
            data.append({
                'id': settlement.id,
                'vendor_name': settlement.vendor.store_name,
                'amount': str(settlement.amount),
                'payout_date': settlement.payout_date.isoformat(),
                'status': settlement.status,
            })
        
        return paginator.get_paginated_response(data)

    @swagger_auto_schema(
        operation_id="admin_disputes_list",
        operation_summary="Disputes & Refunds List",
        operation_description="Retrieve customer disputes and refund requests.",
        tags=["Admin Settlements"],
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description='Filter by status: PENDING, APPROVED, REJECTED'
            ),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=20),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=0),
        ],
        responses={
            200: openapi.Response("Disputes retrieved"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def disputes(self, request):
        """Get disputes list"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Dispute
        from rest_framework.pagination import LimitOffsetPagination
        
        disputes = Dispute.objects.select_related(
            'order', 'customer', 'vendor'
        ).order_by('-created_at')
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter and status_filter.upper() in ['PENDING', 'APPROVED', 'REJECTED']:
            disputes = disputes.filter(status=status_filter.upper())
        
        # Paginate
        paginator = LimitOffsetPagination()
        paginated = paginator.paginate_queryset(disputes, request)
        
        data = []
        for dispute in paginated:
            data.append({
                'id': dispute.id,
                'order_id': str(dispute.order.order_id),
                'customer_name': dispute.customer.full_name,
                'vendor_name': dispute.vendor.store_name,
                'amount': str(dispute.amount),
                'reason': dispute.reason,
                'status': dispute.status,
                'created_at': dispute.created_at.isoformat(),
            })
        
        return paginator.get_paginated_response(data)

    @swagger_auto_schema(
        operation_id="admin_resolve_dispute",
        operation_summary="Resolve Dispute",
        operation_description="Approve or reject a customer dispute/refund request.",
        tags=["Admin Settlements"],
        request_body=DisputeResolutionSerializer,
        responses={
            200: openapi.Response("Dispute resolved successfully"),
            400: openapi.Response("Invalid request"),
            403: openapi.Response("Admin access only"),
            404: openapi.Response("Dispute not found"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"], url_path=r"disputes/(?P<dispute_id>[^/]+)/resolve")
    def resolve_dispute(self, request, dispute_id=None):
        """Resolve a dispute"""
        admin = self.get_admin(request)
        if not admin:
            return Response(
                {"success": False, "message": "Admin access only"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        from transactions.models import Dispute, Wallet
        from django.utils import timezone
        
        try:
            dispute = Dispute.objects.get(id=dispute_id)
        except Dispute.DoesNotExist:
            return Response(
                {"success": False, "message": "Dispute not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        serializer = DisputeResolutionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        action = serializer.validated_data['action']
        admin_note = serializer.validated_data.get('admin_note', '')
        
        # Update dispute
        dispute.status = 'APPROVED' if action == 'APPROVE' else 'REJECTED'
        dispute.admin_note = admin_note
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save()
        
        # If approved, process refund
        if action == 'APPROVE':
            # Credit customer wallet
            customer_wallet, _ = Wallet.objects.get_or_create(user=dispute.customer)
            customer_wallet.credit(dispute.amount, source=f"Refund for Order {dispute.order.order_id}")
            
            # Debit vendor wallet (if they haven't withdrawn yet)
            vendor_wallet, _ = Wallet.objects.get_or_create(user=dispute.vendor.user)
            try:
                vendor_wallet.debit(dispute.amount, source=f"Refund reversal for Order {dispute.order.order_id}")
            except ValueError:
                # If vendor wallet is insufficient, log it
                pass
        
        return Response(
            {
                "success": True,
                "message": f"Dispute {action.lower()}ed successfully"
            },
            status=status.HTTP_200_OK,
        )
