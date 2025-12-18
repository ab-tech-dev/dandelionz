from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

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
    AdminProfileResponseSerializer
)
from transactions.serializers import PaymentSerializer
from users.services.profile_resolver import ProfileResolver
from transactions.models import PayoutRecord

class CustomerProfileViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_customer(self, request):
        """
        Returns a guaranteed customer profile or None if role is invalid.
        """
        return ProfileResolver.resolve_customer(request.user)

    # -----------------------------
    # GET /api/customer/profile/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Get Customer Profile",
        responses={200: CustomerProfileSerializer()},
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

    # -----------------------------
    # PUT /api/customer/profile/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Update Customer Profile",
        request_body=CustomerProfileUpdateSerializer,
        responses={200: CustomerProfileSerializer()},
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

    # -----------------------------
    # PATCH /api/customer/profile/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Partially Update Customer Profile",
        request_body=CustomerProfileUpdateSerializer,
        responses={200: CustomerProfileSerializer()},
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

    # -----------------------------
    # POST /api/customer/change-password/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Change Account Password",
        request_body=ChangePasswordSerializer,
        responses={200: openapi.Response("Password changed successfully")},
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




from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema

from decimal import Decimal
from users.models import Vendor, Notification
from transactions.models import Wallet, TransactionLog, Refund
from users.serializers import (
    VendorProfileSerializer,
    ChangePasswordSerializer,
    NotificationSerializer,
)
from store.models import Product
from store.serializers import ProductSerializer, CreateProductSerializer
from users.services.services import ProfileService

from django.db.models import Sum, F
import logging

logger = logging.getLogger(__name__)


class VendorViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_vendor(self, request):
        """
        Returns a guaranteed vendor profile or None if role is invalid.
        """
        return ProfileResolver.resolve_vendor(request.user)

    # ============================
    # PROFILE
    # ============================

    @swagger_auto_schema(
        operation_description="Retrieve vendor profile of the authenticated vendor.",
        responses={200: VendorProfileSerializer()},
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
        operation_description="Full vendor profile update.",
        request_body=VendorProfileSerializer,
        responses={200: VendorProfileSerializer()},
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
        operation_description="Partial vendor profile update.",
        request_body=VendorProfileSerializer,
        responses={200: VendorProfileSerializer()},
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
        operation_description="Change vendor password.",
        request_body=ChangePasswordSerializer,
        responses={200: "Password changed successfully"},
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
    # PRODUCTS
    # ============================

    @swagger_auto_schema(
        method="post",
        operation_description="Vendor adds a new product to their store.",
        request_body=CreateProductSerializer,
        responses={201: CreateProductSerializer()},
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
        operation_description="Vendor lists all products in their store.",
        responses={200: ProductSerializer(many=True)},
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
        operation_description="Update an existing product.",
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
        security=[{"Bearer": []}],
    )
    @swagger_auto_schema(
        method="patch",
        operation_description="Partial update to an existing product.",
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
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
        operation_description="Delete a product belonging to the vendor.",
        responses={200: "Product deleted"},
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
    # ORDERS
    # ============================
    @swagger_auto_schema(
        method="get",
        operation_description="Vendor orders grouped by status.",
        responses={200: "Order summary"},
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
    # ANALYTICS
    # ============================

    @swagger_auto_schema(
        method="get",
        operation_description="Vendor revenue and top products.",
        responses={200: "Analytics summary"},
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
        operation_description="List vendor notifications.",
        responses={200: NotificationSerializer(many=True)},
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
    permission_classes = [IsAuthenticated]

    def get_admin(self, request):
        admin = ProfileResolver.resolve_admin(request.user)
        if not admin:
            return None
        return admin

    def get_user_by_uuid(self, user_uuid):
        return User.objects.filter(uuid=user_uuid).first()


class AdminProfileViewSet(AdminBaseViewSet):

    @swagger_auto_schema(
        operation_summary="Retrieve business admin profile",
        tags=["Admin Profile"],
        responses={200: BusinessAdminProfileSerializer()},
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
        operation_summary="Change admin password",
        tags=["Admin Profile"],
        request_body=ChangePasswordSerializer,
        responses={200: openapi.Response("Password changed successfully")},
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

    @swagger_auto_schema(
        operation_summary="List all vendors",
        tags=["Vendor Management"],
        responses={200: AdminVendorListSerializer(many=True)},
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
        operation_summary="Approve or unapprove vendor",
        tags=["Vendor Management"],
        request_body=AdminVendorApprovalSerializer,
        responses={200: AdminVendorActionResponseSerializer()},
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
        operation_summary="Suspend or activate a user",
        tags=["Vendor Management"],
        request_body=AdminVendorSuspendSerializer,
        responses={200: AdminVendorActionResponseSerializer()},
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
        operation_summary="Verify vendor KYC",
        tags=["Vendor Management"],
        request_body=AdminVendorKYCSerializer,
        responses={200: AdminVendorActionResponseSerializer()},
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

    @swagger_auto_schema(
        operation_summary="List all marketplace products",
        tags=["Marketplace"],
        responses={200: AdminProductListSerializer(many=True)},
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
        operation_summary="Update product (PUT)",
        request_body=AdminProductUpdateSerializer,
        responses={200: openapi.Response("Updated successfully")}
    )
    @swagger_auto_schema(
        method='patch',
        operation_summary="Update product (PATCH)",
        request_body=AdminProductUpdateSerializer,
        responses={200: openapi.Response("Updated successfully")}
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
        operation_summary="Delete a product",
        tags=["Marketplace"],
        manual_parameters=[openapi.Parameter("slug", openapi.IN_PATH, description="Product slug", type=openapi.TYPE_STRING)],
        responses={200: AdminProductActionResponseSerializer()},
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

    @swagger_auto_schema(
        operation_summary="Get orders summary",
        tags=["Orders & Logistics"],
        responses={200: AdminOrdersSummarySerializer()},
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
        operation_summary="Assign logistics to an order",
        tags=["Orders & Logistics"],
        request_body=AdminOrderActionSerializer,
        responses={200: AdminOrderActionResponseSerializer()},
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
        operation_summary="Process refund for an order",
        tags=["Orders & Logistics"],
        request_body=AdminOrderActionSerializer,
        responses={200: AdminOrderActionResponseSerializer()},
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

    @action(detail=False, methods=["get"])
    def payments(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        payments = Payment.objects.all()
        serializer = PaymentSerializer(payments, many=True)
        return Response({"success": True, "data": serializer.data})

    @action(detail=False, methods=["post"])
    def trigger_payout(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"message": "Access denied"}, status=403)

        serializer = TriggerPayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_user_by_uuid(serializer.validated_data["user_uuid"])
        if not user:
            return Response({"message": "User not found"}, status=404)

        total_payable = PayoutService.calculate_payout(user)
        if total_payable <= 0:
            return Response({"message": "Nothing to payout"}, status=400)

        PayoutService.execute_payout(user, total_payable)

        return Response({"success": True, "amount": total_payable})




from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class AdminFinanceViewSet(AdminBaseViewSet):

    @swagger_auto_schema(
        operation_summary="Get all payments",
        tags=["Finance"],
        responses={200: AdminFinancePaymentSerializer(many=True)},
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
        operation_summary="Trigger payout for vendor or customer",
        tags=["Finance"],
        request_body=AdminFinancePayoutSerializer,
        responses={200: openapi.Response("Payout triggered")},
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

    @swagger_auto_schema(
        operation_summary="Admin sales & orders analytics overview",
        tags=["Analytics"],
        responses={200: AdminAnalyticsSerializer()},
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
