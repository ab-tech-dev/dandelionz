from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils import timezone

from store.serializers import ProductSerializer, CreateProductSerializer

from users.serializers import (
    CustomerProfileSerializer,
    CustomerProfileUpdateSerializer,
    ChangePasswordSerializer,
    AdminAnalyticsSerializer,
    AdminFinancePayoutSerializer,
    AdminFinancePaymentSerializer,
    AdminOrderActionSerializer,
    AdminOrderActionResponseSerializer,
    AdminOrdersSummarySerializer,
    AdminProductActionResponseSerializer,
    AdminProductUpdateRequestSerializer,
    AdminProductListSerializer,
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
)
from transactions.serializers import PaymentSerializer
from users.services.profile_resolver import ProfileResolver
from transactions.models import PayoutRecord, Order, Payment
from users.models import Notification
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
        serializer.save(store=vendor)

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

        products = Product.objects.filter(store=vendor)
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
            product = Product.objects.get(pk=pk, store=vendor)
        except Product.DoesNotExist:
            return Response(
                {"success": False, "message": "Product not found"},
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
            product = Product.objects.get(pk=pk, store=vendor)
            product.delete()
        except Product.DoesNotExist:
            return Response(
                {"success": False, "message": "Product not found"},
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

        orders = Order.objects.filter(
            order_items__product__store=vendor
        ).distinct()

        data = {
            "pending": orders.filter(status=Order.Status.PENDING).count(),
            "paid": orders.filter(status=Order.Status.PAID).count(),
            "shipped": orders.filter(status=Order.Status.SHIPPED).count(),
            "delivered": orders.filter(status=Order.Status.DELIVERED).count(),
            "canceled": orders.filter(status=Order.Status.CANCELED).count(),
        }

        return Response({"success": True, "data": data})

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
            recipient=request.user
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
from users.models import Notification
from store.models import Product
from django.db import models
from users.serializers import VendorApprovalSerializer
from django.contrib.auth import get_user_model
User = get_user_model()
from users.serializers import TriggerPayoutSerializer, OrderActionSerializer, AdminProductUpdateSerializer, VendorKYCSerializer, SuspendUserSerializer, BusinessAdminProfileSerializer
from users.services.payout_service import PayoutService

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from users.services.profile_resolver import ProfileResolver


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
        Notification.objects.create(
            recipient=delivery_agent.user,
            title="New Order Assignment",
            message=f"You have been assigned order {order.order_id} for delivery."
        )

        # Notify customer
        Notification.objects.create(
            recipient=order.customer,
            title="Delivery Agent Assigned",
            message=f"A delivery agent has been assigned to your order {order.order_id}."
        )

        return Response({
            "success": True,
            "message": "Delivery agent assigned successfully",
            "order_id": str(order.order_id),
            "delivery_agent": delivery_agent.user.full_name
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
        from store.models import Product
        
        data = {
            "total_users": CustomUser.objects.filter(role='CUSTOMER').count(),
            "total_vendors": Vendor.objects.count(),
            "total_orders": Order.objects.count(),
            "total_products": Product.objects.count(),
        }

        serializer = AdminAnalyticsSerializer(data)
        return Response({"success": True, "data": serializer.data})


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
        
        order.status = Order.Status.DELIVERED
        order.save(update_fields=['status', 'updated_at'])
        
        # Create notification for customer
        Notification.objects.create(
            recipient=order.customer,
            title="Order Delivered",
            message=f"Your order {order.order_id} has been delivered."
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
        
        notifications = Notification.objects.filter(recipient=agent.user).order_by('-created_at')[:50]
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
            recipient=self.request.user
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
                recipient=self.request.user
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
            recipient=request.user,
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
            recipient=request.user,
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
        operation_description="""
        Create a notification with three possible actions:
        1. Send Immediately: status='Sent', scheduled_at=null
        2. Save as Draft: status='Draft'
        3. Schedule for Later: status='Scheduled', scheduled_at='2026-01-25T10:00:00Z'
        
        Recipients can be USERS, VENDORS, or ALL.
        """,
        tags=["Admin Notifications"],
        request_body=AdminNotificationCreateSerializer,
        responses={
            201: openapi.Response(
                "Notification created/scheduled successfully",
                AdminNotificationCreateSerializer()
            ),
            400: openapi.Response("Invalid data or validation error"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    def create(self, request):
        """Create a notification (send, draft, or schedule)"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminNotificationCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        notification = serializer.save()

        # Handle different notification statuses
        status_code = status.HTTP_201_CREATED
        message = "Notification created successfully"

        if notification.status == 'Sent':
            # Send notification immediately to recipients
            self._send_notification_to_recipients(notification)
            message = "Notification sent to recipients"

        elif notification.status == 'Draft':
            message = "Notification saved as draft"

        elif notification.status == 'Scheduled':
            # Schedule the notification to be sent later using Celery
            from users.tasks import send_scheduled_notification
            send_scheduled_notification.apply_async(
                args=[notification.id],
                eta=notification.scheduled_at
            )
            message = f"Notification scheduled for {notification.scheduled_at}"

        return Response({
            "success": True,
            "data": AdminNotificationCreateSerializer(notification).data,
            "message": message
        }, status=status_code)

    def _send_notification_to_recipients(self, notification):
        """
        Send notification immediately to the specified recipient group.
        Creates individual Notification records for each recipient.
        """
        from users.models import Vendor
        from authentication.models import CustomUser

        recipients = []

        if notification.recipient_type == 'ALL':
            # Send to all active users
            recipients = CustomUser.objects.filter(is_active=True, status='ACTIVE')

        elif notification.recipient_type == 'USERS':
            # Send to all customers (non-vendor, non-admin users)
            recipients = CustomUser.objects.filter(
                is_active=True,
                status='ACTIVE',
                role=CustomUser.Role.CUSTOMER
            )

        elif notification.recipient_type == 'VENDORS':
            # Send to all vendors
            vendor_user_ids = Vendor.objects.filter(
                vendor_status='approved'
            ).values_list('user_id', flat=True)
            recipients = CustomUser.objects.filter(
                uuid__in=vendor_user_ids,
                is_active=True,
                status='ACTIVE'
            )

        # Create individual notifications for each recipient
        notifications_to_create = [
            Notification(
                recipient=recipient,
                title=notification.title,
                message=notification.message,
                status='Sent',
                created_at=timezone.now()
            )
            for recipient in recipients
        ]

        if notifications_to_create:
            Notification.objects.bulk_create(notifications_to_create, batch_size=1000)
            logger.info(
                f"[AdminNotification] Sent to {len(notifications_to_create)} "
                f"recipients (type: {notification.recipient_type})"
            )

    @swagger_auto_schema(
        operation_id="admin_list_notifications",
        operation_summary="List Admin Notifications",
        operation_description="Retrieve all admin broadcast notifications with their status and scheduling details.",
        tags=["Admin Notifications"],
        manual_parameters=[
            openapi.Parameter(
                'status',
                openapi.IN_QUERY,
                description="Filter by notification status: Sent, Draft, or Scheduled",
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
        """List all admin broadcast notifications"""
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        # Filter broadcast notifications (those with recipient_type set)
        notifications = Notification.objects.filter(
            recipient_type__isnull=False
        ).select_related('created_by').order_by('-created_at')

        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            notifications = notifications.filter(status=status_filter)

        serializer = AdminNotificationListSerializer(notifications, many=True)

        return Response({
            "success": True,
            "data": serializer.data,
            "count": notifications.count()
        })

