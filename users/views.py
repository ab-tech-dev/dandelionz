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
)
from users.services.profile_resolver import ProfileResolver


class CustomerProfileViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_customer(self, request):
        """
        Returns a guaranteed customer profile or None if role is invalid.
        """
        return ProfileResolver.resolve(request.user)

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
from store.serializers import ProductSerializer
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
        return ProfileResolver.resolve(request.user)

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
        request_body=ProductSerializer,
        responses={201: ProductSerializer()},
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

        serializer = ProductSerializer(data=request.data)
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

        orders = Order.objects.filter(vendor=vendor)

        data = {
            "pending": orders.filter(status="pending").count(),
            "shipped": orders.filter(status="shipped").count(),
            "delivered": orders.filter(status="delivered").count(),
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
    ProductSerializer,
    PaymentSerializer,
)
from .services import ProfileService, AdminService
from users.models import Vendor, Customer, Wallet
from transactions.models import Order, Refund
from transactions.models import Payment, TransactionLog
from users.models import Notification
from store.models import Product
from django.db import models

class BusinessAdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # ================= UTILITIES =================
    def get_admin(self, request):
        """Return authenticated business admin user."""
        return ProfileResolver.get_admin(request.user)

    def get_vendor_by_uuid(self, vendor_uuid):
        try:
            return Vendor.objects.filter(uuid=vendor_uuid, is_active=True).first()
        except ValueError:
            return None

    def get_user_by_uuid(self, user_uuid):
        return Vendor.objects.filter(uuid=user_uuid).first() or Customer.objects.filter(uuid=user_uuid).first()

    # ================= PROFILE =================
    @swagger_auto_schema(
        operation_summary="Retrieve business admin profile",
        tags=["Admin Profile"],
        responses={200: AdminUserManagementSerializer()},
        security=[{"Bearer": []}],
    )
    def retrieve(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "You are not a business admin"}, status=403)
        serializer = AdminUserManagementSerializer(request.user)
        return Response({"success": True, "data": serializer.data})

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
            return Response({"success": False, "message": "Access denied"}, status=403)

        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ProfileService.process_password_change(
            admin,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )
        return Response(result, status=status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST)

    # ================= NOTIFICATIONS =================
    @swagger_auto_schema(
        operation_summary="Get all admin notifications",
        tags=["Notifications"],
        responses={200: NotificationSerializer(many=True)},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def notifications(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        notifications = Notification.objects.filter(recipient=admin).order_by("-created_at")
        serializer = NotificationSerializer(notifications, many=True)
        return Response({"success": True, "data": serializer.data})

    # ================= VENDOR MANAGEMENT =================
    @swagger_auto_schema(
        operation_summary="List all vendors",
        tags=["Vendor Management"],
        responses={200: VendorProfileSerializer(many=True)},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_vendors(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        vendors = Vendor.objects.filter(is_active=True)
        serializer = VendorProfileSerializer(vendors, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_summary="Approve or un-approve vendor",
        tags=["Vendor Management"],
        manual_parameters=[openapi.Parameter("vendor_uuid", openapi.IN_PATH, description="Vendor UUID", type=openapi.TYPE_STRING)],
        responses={200: openapi.Response("Vendor approved/unapproved")},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["post"], url_path='approve_vendor/(?P<vendor_uuid>[^/.]+)')
    def approve_vendor(self, request, vendor_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        vendor = self.get_vendor_by_uuid(vendor_uuid)
        if not vendor:
            return Response({"success": False, "message": "Vendor not found"}, status=404)
        with transaction.atomic():
            vendor.is_verified_vendor = not vendor.is_verified_vendor
            vendor.save()
        return Response({"success": True, "message": f"Vendor {'approved' if vendor.is_verified_vendor else 'unapproved'}"})

    @swagger_auto_schema(
        operation_summary="Suspend or activate user (vendor or customer)",
        tags=["Vendor Management"],
        manual_parameters=[openapi.Parameter("user_uuid", openapi.IN_PATH, description="User UUID", type=openapi.TYPE_STRING)],
        responses={200: openapi.Response("User suspended or activated")},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["post"], url_path='suspend_user/(?P<user_uuid>[^/.]+)')
    def suspend_user(self, request, user_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        user_obj = self.get_user_by_uuid(user_uuid)
        if not user_obj:
            return Response({"success": False, "message": "User not found"}, status=404)
        user_obj.user.is_active = not user_obj.user.is_active
        user_obj.user.save()
        return Response({"success": True, "message": f"User {'suspended' if not user_obj.user.is_active else 'activated'}"})

    @swagger_auto_schema(
        operation_summary="Verify vendor KYC",
        tags=["Vendor Management"],
        manual_parameters=[openapi.Parameter("vendor_uuid", openapi.IN_PATH, description="Vendor UUID", type=openapi.TYPE_STRING)],
        responses={200: openapi.Response("KYC verified")},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["post"], url_path='verify_kyc/(?P<vendor_uuid>[^/.]+)')
    def verify_kyc(self, request, vendor_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        vendor = self.get_vendor_by_uuid(vendor_uuid)
        if not vendor:
            return Response({"success": False, "message": "Vendor not found"}, status=404)
        with transaction.atomic():
            vendor.is_verified_vendor = True
            vendor.save()
        return Response({"success": True, "message": "Vendor KYC verified"})

    # ================= MARKETPLACE MANAGEMENT =================
    @swagger_auto_schema(
        operation_summary="List marketplace products",
        tags=["Marketplace"],
        responses={200: ProductSerializer(many=True)},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def list_products(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        method="put",
        operation_summary="Update product",
        tags=["Marketplace"],
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
        security=[{"Bearer": []}],
    )
    @swagger_auto_schema(
        method="patch",
        operation_summary="Partially update product",
        tags=["Marketplace"],
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["put", "patch"], url_path='update_product/(?P<product_uuid>[^/.]+)')
    def update_product(self, request, product_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        success, data = AdminService.update_product(product_uuid, request.data)
        status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
        return Response({"success": success, "data": data}, status=status_code)

    # ================= ORDERS & LOGISTICS =================
    @swagger_auto_schema(
        operation_summary="Get orders summary",
        tags=["Orders & Logistics"],
        responses={200: openapi.Response("Orders summary")},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def orders(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        orders = Order.objects.all()
        data = {
            "pending": orders.filter(status="pending").count(),
            "shipped": orders.filter(status="shipped").count(),
            "delivered": orders.filter(status="delivered").count(),
        }
        return Response({"success": True, "data": data})

    def get_order_by_uuid(self, order_uuid):
        try:
            return Order.objects.filter(uuid=order_uuid).first()
        except ValueError:
            return None

    @swagger_auto_schema(
        operation_summary="Assign logistics to an order",
        tags=["Orders & Logistics"],
        manual_parameters=[openapi.Parameter("order_uuid", openapi.IN_PATH, description="Order UUID", type=openapi.TYPE_STRING)],
        responses={200: openapi.Response("Logistics assigned")},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["post"], url_path='assign_logistics/(?P<order_uuid>[^/.]+)')
    def assign_logistics(self, request, order_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        order = self.get_order_by_uuid(order_uuid)
        if not order:
            return Response({"success": False, "message": "Order not found"}, status=404)
        with transaction.atomic():
            order.logistics_assigned = True
            order.save()
        return Response({"success": True, "message": "Logistics assigned successfully"})

    @swagger_auto_schema(
        operation_summary="Process refund for an order",
        tags=["Orders & Logistics"],
        manual_parameters=[openapi.Parameter("order_uuid", openapi.IN_PATH, description="Order UUID", type=openapi.TYPE_STRING)],
        responses={200: openapi.Response("Refund processed")},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["post"], url_path='process_refund/(?P<order_uuid>[^/.]+)')
    def process_refund(self, request, order_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        order = self.get_order_by_uuid(order_uuid)
        if not order:
            return Response({"success": False, "message": "Order not found"}, status=404)
        with transaction.atomic():
            order.status = "refunded"
            order.save()
        return Response({"success": True, "message": "Refund processed successfully"})

    # ================= FINANCE =================
    @swagger_auto_schema(
        operation_summary="Get payments summary",
        tags=["Finance"],
        responses={200: "Payments summary"},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def payments(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        payments = Payment.objects.all()
        serializer = PaymentSerializer(payments, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_summary="Trigger payout for vendor or customer",
        tags=["Finance"],
        manual_parameters=[openapi.Parameter("user_uuid", openapi.IN_PATH, description="User UUID", type=openapi.TYPE_STRING)],
        responses={200: "Payout triggered"},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["post"], url_path='trigger_payout/(?P<user_uuid>[^/.]+)')
    def trigger_payout(self, request, user_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)

        user_obj = self.get_user_by_uuid(user_uuid)
        if not user_obj:
            return Response({"success": False, "message": "User not found"}, status=404)

        user = user_obj.user
        total_payable = Decimal("0")
        payout_type = ""

        # Vendor payout
        if isinstance(user_obj, Vendor):
            pending_refunds = Refund.objects.filter(
                payment__order__order_items__product__vendor=user_obj,
                status="PENDING"
            ).exists()
            if pending_refunds:
                return Response({"success": False, "message": "Cannot trigger payout: Vendor has orders with pending refunds."}, status=400)
            vendor_orders = Order.objects.filter(order_items__product__vendor=user_obj, payment__status="SUCCESS").distinct()
            for order in vendor_orders:
                for item in order.order_items.all():
                    if item.vendor == user_obj:
                        total_payable += item.item_subtotal * Decimal("0.90")
            payout_type = "Vendor Payout"

        # Customer referral
        elif isinstance(user_obj, Customer):
            total_payable = getattr(user_obj.wallet, 'balance', Decimal("0"))
            if total_payable <= 0:
                return Response({"success": False, "message": "No referral bonus or balance available."}, status=400)
            payout_type = "Referral Bonus Payout"

        # Credit wallet and notify
        wallet, _ = Wallet.objects.get_or_create(user=user)
        if total_payable > 0:
            wallet.credit(total_payable, source=payout_type)
            Notification.objects.create(recipient=user, title=f"{payout_type} Credited", message=f"A payout of {total_payable} has been credited to your wallet.")
            TransactionLog.objects.create(order=None, message=f"{payout_type} of {total_payable} triggered for user {user.email}", level="INFO")

        return Response({"success": True, "message": f"{payout_type} of {total_payable} triggered for user {user.email}"})

    @swagger_auto_schema(
        operation_summary="Get settlements summary",
        tags=["Finance"],
        responses={200: "Settlement summary"},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def settlements(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        settlements = Payment.objects.values("vendor__store_name").annotate(total_paid=models.Sum("amount"))
        return Response({"success": True, "data": settlements})

    @swagger_auto_schema(
        operation_summary="Get settlements for a specific vendor",
        tags=["Finance"],
        manual_parameters=[openapi.Parameter("vendor_uuid", openapi.IN_PATH, description="Vendor UUID", type=openapi.TYPE_STRING)],
        responses={200: "Vendor settlement details"},
        security=[{"Bearer": []}],
    )
    @action(detail=True, methods=["get"], url_path='vendor_settlements/(?P<vendor_uuid>[^/.]+)')
    def vendor_settlements(self, request, vendor_uuid=None):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        vendor = self.get_vendor_by_uuid(vendor_uuid)
        if not vendor:
            return Response({"success": False, "message": "Vendor not found"}, status=404)
        settlements = Payment.objects.filter(vendor=vendor).aggregate(total_paid=models.Sum("amount"))
        return Response({"success": True, "data": settlements})

    # ================= ANALYTICS =================
    @swagger_auto_schema(
        operation_summary="Admin sales & orders analytics",
        tags=["Analytics"],
        responses={200: "Sales analytics"},
        security=[{"Bearer": []}],
    )
    @action(detail=False, methods=["get"])
    def analytics(self, request):
        admin = self.get_admin(request)
        if not admin:
            return Response({"success": False, "message": "Access denied"}, status=403)
        data = {
            "total_orders": Order.objects.count(),
            "total_revenue": Payment.objects.aggregate(total=models.Sum("amount"))["total"] or 0,
            "pending_orders": Order.objects.filter(status="pending").count(),
            "delivered_orders": Order.objects.filter(status="delivered").count(),
        }
        return Response({"success": True, "data": data})

