from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

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
    AdminVendorApprovalSerializer,
    AdminVendorActionResponseSerializer,
    AdminVendorSuspendSerializer,
    AdminVendorKYCSerializer,
    AdminProfileResponseSerializer,
    NotificationSerializer,
    VendorProfileSerializer,
    VendorOrdersSummaryResponseSerializer,
    VendorAnalyticsResponseSerializer,
    AdminFinancePayoutResponseSerializer,
    SuccessResponseSerializer,
)
from transactions.serializers import PaymentSerializer
from users.services.profile_resolver import ProfileResolver
from transactions.models import PayoutRecord
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
        operation_description="Update specific fields of the customer profile. Only provide the fields you want to update.",
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
        operation_summary="Assign Logistics to Order",
        operation_description="Mark an order as having logistics assigned and ready for shipment.",
        tags=["Orders & Logistics"],
        request_body=AdminOrderActionSerializer,
        responses={
            200: openapi.Response(
                "Logistics assigned successfully",
                AdminOrderActionResponseSerializer()
            ),
            400: openapi.Response("Invalid request data"),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["post"])
    def assign_logistics(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = AdminOrderActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = Order.objects.filter(uuid=serializer.validated_data["order_uuid"]).first()
        if not order:
            return Response({"success": False, "message": "Order not found"}, status=404)

        order.logistics_assigned = True
        order.save(update_fields=["logistics_assigned"])

        response_serializer = AdminOrderActionResponseSerializer({"success": True})
        return Response(response_serializer.data)

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
        operation_summary="Admin Sales & Orders Analytics Overview",
        operation_description="Get platform-wide analytics including total orders, revenue, pending and delivered orders.",
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

        data = {
            "total_orders": Order.objects.count(),
            "total_revenue": Payment.objects.aggregate(total=models.Sum("amount"))["total"] or 0,
            "pending_orders": Order.objects.filter(status="pending").count(),
            "delivered_orders": Order.objects.filter(status="delivered").count(),
        }

        serializer = AdminAnalyticsSerializer(data)
        return Response({"success": True, "data": serializer.data})
