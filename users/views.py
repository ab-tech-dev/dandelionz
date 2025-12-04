from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .serializers import (
    CustomerProfileSerializer,
    CustomerProfileUpdateSerializer,
    ChangePasswordSerializer
)
from transactions.serializers import PaymentSerializer


class CustomerProfileViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_customer(self, request):
        return request.user.customer

    # -----------------------------
    # GET /api/customer/profile/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Get Customer Profile",
        operation_description="Returns the authenticated customer's full profile data.",
        responses={200: CustomerProfileSerializer()},
    )
    def list(self, request):
        customer = self.get_customer(request)
        serializer = CustomerProfileSerializer(customer)
        return Response(serializer.data, status=200)

    # -----------------------------
    # PUT /api/customer/profile/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Update Customer Profile",
        operation_description="Replaces the customer profile with the provided data.",
        request_body=CustomerProfileUpdateSerializer,
        responses={
            200: CustomerProfileSerializer(),
            400: "Invalid data format"
        },
    )
    def update(self, request):
        customer = self.get_customer(request)
        serializer = CustomerProfileUpdateSerializer(customer, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(CustomerProfileSerializer(customer).data, status=200)

    # -----------------------------
    # PATCH /api/customer/profile/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Partially Update Customer Profile",
        operation_description="Updates only the supplied fields.",
        request_body=CustomerProfileUpdateSerializer,
        responses={200: CustomerProfileSerializer()},
    )
    def partial_update(self, request):
        customer = self.get_customer(request)
        serializer = CustomerProfileUpdateSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(CustomerProfileSerializer(customer).data, status=200)

    # -----------------------------
    # POST /api/customer/change-password/
    # -----------------------------
    @swagger_auto_schema(
        operation_summary="Change Account Password",
        operation_description="Allows authenticated customers to change their password.",
        request_body=ChangePasswordSerializer,
        responses={
            200: openapi.Response("Password changed successfully"),
            400: "Incorrect password"
        },
    )
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"detail": "Incorrect password"}, status=400)

        user.set_password(serializer.validated_data["new_password"])
        user.save()

        return Response({"message": "Password changed successfully"}, status=200)




from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response

from users.serializers import (
    NotificationSerializer,
    ChangePasswordSerializer,
    VendorProfileSerializer,
)

from store.serializers import ProductSerializer
from users.models import Vendor, Notification
from users.services import ProfileService, AdminService
from store.models import Product

from django.db.models import Sum, F
from drf_yasg.utils import swagger_auto_schema

import logging
logger = logging.getLogger(__name__)


class VendorViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # ============================
    # PROFILE
    # ============================

    @swagger_auto_schema(
        operation_description="Retrieve vendor profile of the authenticated vendor.",
        responses={200: VendorProfileSerializer()},
    )
    def retrieve(self, request):
        if not request.user.is_vendor:
            return Response(
                {"success": False, "message": "Access denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = ProfileService.get_profile(user=request.user, request=request)
        return Response({"success": True, "data": data}, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Full vendor profile update.",
        request_body=VendorProfileSerializer,
        responses={200: VendorProfileSerializer()},
    )
    def update(self, request):
        success, data, code = ProfileService.update_profile(
            user=request.user,
            data=request.data,
            files=request.FILES,
            request=request,
        )
        return Response(data, status=code)

    @swagger_auto_schema(
        operation_description="Partial vendor profile update.",
        request_body=VendorProfileSerializer,
        responses={200: VendorProfileSerializer()},
    )
    def partial_update(self, request):
        return self.update(request)

    @swagger_auto_schema(
        method="post",
        operation_description="Change vendor password.",
        request_body=ChangePasswordSerializer,
        responses={200: "Password changed successfully"},
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        current_password = request.data.get("current_password")
        new_password = request.data.get("new_password")

        result = ProfileService.process_password_change(
            request.user, current_password, new_password
        )
        status_code = (
            status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST
        )
        return Response(result, status=status_code)

    # ============================
    # PRODUCTS
    # ============================

    @swagger_auto_schema(
        method="post",
        operation_description="Vendor adds a new product to their store.",
        request_body=ProductSerializer,
        responses={201: ProductSerializer()},
    )
    @action(detail=False, methods=["post"])
    def add_product(self, request):
        serializer = ProductSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(store=request.user.vendor_profile)
            return Response(
                {"success": True, "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @swagger_auto_schema(
        method="get",
        operation_description="Vendor lists all products in their store.",
        responses={200: ProductSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def list_products(self, request):
        products = Product.objects.filter(store=request.user.vendor_profile)
        serializer = ProductSerializer(products, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        method="put",
        operation_description="Update an existing product.",
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
    )
    @swagger_auto_schema(
        method="patch",
        operation_description="Partial update to an existing product.",
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
    )
    @action(detail=True, methods=["put", "patch"])
    def update_product(self, request, pk=None):
        try:
            product = Product.objects.get(pk=pk, store=request.user.vendor_profile)
        except Product.DoesNotExist:
            return Response(
                {"success": False, "message": "Product not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ProductSerializer(product, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "data": serializer.data})

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @swagger_auto_schema(
        method="delete",
        operation_description="Delete a product belonging to the vendor.",
        responses={200: "Product deleted"},
    )
    @action(detail=True, methods=["delete"])
    def delete_product(self, request, pk=None):
        try:
            product = Product.objects.get(pk=pk, store=request.user.vendor_profile)
            product.delete()
            return Response({"success": True, "message": "Product deleted"})
        except Product.DoesNotExist:
            return Response(
                {"success": False, "message": "Product not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    # ============================
    # ORDERS
    # ============================

    @swagger_auto_schema(
        method="get",
        operation_description="Vendor orders grouped by status.",
        responses={200: "Order summary"},
    )
    @action(detail=False, methods=["get"])
    def orders(self, request):
        try:
            from transactions.models import Order
            orders = Order.objects.filter(vendor=request.user.vendor_profile)

            data = {
                "pending": orders.filter(status="pending").count(),
                "shipped": orders.filter(status="shipped").count(),
                "delivered": orders.filter(status="delivered").count(),
            }
            return Response({"success": True, "data": data})

        except Exception as e:
            logger.error(f"Order fetch error: {str(e)}")
            return Response(
                {"success": False, "message": "Failed to fetch orders"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ============================
    # ANALYTICS
    # ============================

    @swagger_auto_schema(
        method="get",
        operation_description="Vendor revenue, total sold, and top products.",
        responses={200: "Analytics summary"},
    )
    @action(detail=False, methods=["get"])
    def analytics(self, request):
        try:
            from transactions.models import OrderItem

            items = OrderItem.objects.filter(
                product__store=request.user.vendor_profile
            )

            total_revenue = (
                items.aggregate(total=Sum(F("product__price") * F("quantity")))[
                    "total"
                ]
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

        except Exception as e:
            logger.error(f"Analytics fetch error: {str(e)}")
            return Response(
                {"success": False, "message": "Failed to fetch analytics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ============================
    # NOTIFICATIONS
    # ============================

    @swagger_auto_schema(
        method="get",
        operation_description="List vendor notifications.",
        responses={200: NotificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def notifications(self, request):
        notifications = Notification.objects.filter(
            recipient=request.user
        ).order_by("-created_at")

        serializer = NotificationSerializer(notifications, many=True)
        return Response({"success": True, "data": serializer.data})


# users/views.py
from django.db import models
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging

from users.models import Vendor, Customer, BusinessAdmin, Notification
from users.serializers import (
    VendorProfileSerializer,
    VendorProfileUpdateSerializer,
    CustomerProfileSerializer,
    AdminUserManagementSerializer,
    NotificationSerializer,
    ChangePasswordSerializer,
)
from store.models import Product
from store.serializers import ProductSerializer
from transactions.models import Order, Payment

logger = logging.getLogger(__name__)


class BusinessAdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    # ===============================================================
    # PROFILE
    # ===============================================================

    @swagger_auto_schema(
        operation_summary="Retrieve business admin profile",
        tags=["Admin Profile"],
        responses={200: AdminUserManagementSerializer()},
    )
    def retrieve(self, request):
        admin_profile = request.user.business_admin_profile
        serializer = AdminUserManagementSerializer(request.user)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_summary="Change admin password",
        tags=["Admin Profile"],
        request_body=ChangePasswordSerializer,
        responses={200: openapi.Response("Password changed successfully")},
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user

        if not user.check_password(serializer.validated_data["current_password"]):
            return Response({"success": False, "message": "Incorrect password"}, status=400)

        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"success": True, "message": "Password changed successfully"})

    # ===============================================================
    # NOTIFICATIONS
    # ===============================================================

    @swagger_auto_schema(
        operation_summary="Get all admin notifications",
        tags=["Notifications"],
        responses={200: NotificationSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def notifications(self, request):
        notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")
        serializer = NotificationSerializer(notifications, many=True)
        return Response({"success": True, "data": serializer.data})

    # ===============================================================
    # VENDOR MANAGEMENT
    # ===============================================================

    @swagger_auto_schema(
        operation_summary="List all vendors",
        tags=["Vendor Management"],
        responses={200: VendorProfileSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def list_vendors(self, request):
        vendors = Vendor.objects.all()
        serializer = VendorProfileSerializer(vendors, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_summary="Approve or un-approve vendor",
        tags=["Vendor Management"],
        manual_parameters=[
            openapi.Parameter("pk", openapi.IN_PATH, description="Vendor ID", type=openapi.TYPE_INTEGER)
        ],
        responses={200: openapi.Response("Vendor approved/unapproved")},
    )
    @action(detail=True, methods=["post"])
    def approve_vendor(self, request, pk=None):
        try:
            vendor = Vendor.objects.get(pk=pk)
            vendor.is_verified_vendor = not vendor.is_verified_vendor
            vendor.save()
            return Response({"success": True, "message": f"Vendor {'approved' if vendor.is_verified_vendor else 'unapproved'}"})
        except Vendor.DoesNotExist:
            return Response({"success": False, "message": "Vendor not found"}, status=404)

    @swagger_auto_schema(
        operation_summary="Suspend or activate user (vendor or customer)",
        tags=["Vendor Management"],
        manual_parameters=[
            openapi.Parameter("pk", openapi.IN_PATH, description="User ID", type=openapi.TYPE_INTEGER)
        ],
        responses={200: openapi.Response("User suspended or activated")},
    )
    @action(detail=True, methods=["post"])
    def suspend_user(self, request, pk=None):
        try:
            user = Vendor.objects.filter(pk=pk).first() or Customer.objects.filter(pk=pk).first()
            if not user:
                return Response({"success": False, "message": "User not found"}, status=404)
            user.user.is_active = not user.user.is_active
            user.user.save()
            return Response({"success": True, "message": f"User {'suspended' if not user.user.is_active else 'activated'}"})
        except Exception as e:
            logger.error(str(e))
            return Response({"success": False, "message": "Error suspending user"}, status=500)

    @swagger_auto_schema(
        operation_summary="Verify vendor KYC",
        tags=["Vendor Management"],
        manual_parameters=[
            openapi.Parameter("pk", openapi.IN_PATH, description="Vendor ID", type=openapi.TYPE_INTEGER)
        ],
        responses={200: openapi.Response("KYC verified")},
    )
    @action(detail=True, methods=["post"])
    def verify_kyc(self, request, pk=None):
        try:
            vendor = Vendor.objects.get(pk=pk)
            vendor.is_verified_vendor = True
            vendor.save()
            return Response({"success": True, "message": "Vendor KYC verified"})
        except Vendor.DoesNotExist:
            return Response({"success": False, "message": "Vendor not found"}, status=404)

    # ===============================================================
    # MARKETPLACE MANAGEMENT
    # ===============================================================

    @swagger_auto_schema(
        operation_summary="List marketplace products",
        tags=["Marketplace"],
        responses={200: ProductSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def list_products(self, request):
        products = Product.objects.all()
        serializer = ProductSerializer(products, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        method="put",
        operation_summary="Update product",
        tags=["Marketplace"],
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
    )
    @swagger_auto_schema(
        method="patch",
        operation_summary="Partially update product",
        tags=["Marketplace"],
        request_body=ProductSerializer,
        responses={200: ProductSerializer()},
    )
    @action(detail=True, methods=["put", "patch"])
    def update_product(self, request, pk=None):
        success, data = AdminService.update_product(pk, request.data)
        status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
        return Response({"success": success, "data": data}, status=status_code)

    # ===============================================================
    # ORDERS & LOGISTICS
    # ===============================================================

    @swagger_auto_schema(
        operation_summary="Get orders summary",
        tags=["Orders & Logistics"],
        responses={200: openapi.Response("Orders summary")},
    )
    @action(detail=False, methods=["get"])
    def orders(self, request):
        orders = Order.objects.all()
        data = {
            "pending": orders.filter(status="pending").count(),
            "shipped": orders.filter(status="shipped").count(),
            "delivered": orders.filter(status="delivered").count(),
        }
        return Response({"success": True, "data": data})

    @swagger_auto_schema(
        operation_summary="Assign logistics to an order",
        tags=["Orders & Logistics"],
        manual_parameters=[
            openapi.Parameter("pk", openapi.IN_PATH, description="Order ID", type=openapi.TYPE_INTEGER)
        ],
        responses={200: openapi.Response("Logistics assigned")},
    )
    @action(detail=True, methods=["post"])
    def assign_logistics(self, request, pk=None):
        try:
            order = Order.objects.get(pk=pk)
            order.logistics_assigned = True
            order.save()
            return Response({"success": True, "message": "Logistics assigned successfully"})
        except Order.DoesNotExist:
            return Response({"success": False, "message": "Order not found"}, status=404)

    @swagger_auto_schema(
        operation_summary="Process refund for an order",
        tags=["Orders & Logistics"],
        manual_parameters=[
            openapi.Parameter("pk", openapi.IN_PATH, description="Order ID", type=openapi.TYPE_INTEGER)
        ],
        responses={200: openapi.Response("Refund processed")},
    )
    @action(detail=True, methods=["post"])
    def process_refund(self, request, pk=None):
        try:
            order = Order.objects.get(pk=pk)
            order.status = "refunded"
            order.save()
            return Response({"success": True, "message": "Refund processed successfully"})
        except Order.DoesNotExist:
            return Response({"success": False, "message": "Order not found"}, status=404)

    # ===============================================================
    # FINANCE
    # ===============================================================

    @swagger_auto_schema(
        operation_summary="Get payments summary",
        tags=["Finance"],
        responses={200: "Payments summary"},
    )
    @action(detail=False, methods=["get"])
    def payments(self, request):
        payments = Payment.objects.all()
        serializer = PaymentSerializer(payments, many=True)
        return Response({"success": True, "data": serializer.data})

    @swagger_auto_schema(
        operation_summary="Trigger vendor payout",
        tags=["Finance"],
        manual_parameters=[
            openapi.Parameter("pk", openapi.IN_PATH, description="Vendor ID", type=openapi.TYPE_INTEGER),
        ],
        responses={200: "Payout triggered"},
    )
    @action(detail=True, methods=["post"])
    def trigger_payout(self, request, pk=None):
        try:
            vendor = Vendor.objects.get(pk=pk)
            return Response({"success": True, "message": f"Payout triggered for vendor {vendor.store_name}"})
        except Vendor.DoesNotExist:
            return Response({"success": False, "message": "Vendor not found"}, status=404)

    @swagger_auto_schema(
        operation_summary="Get settlements summary",
        tags=["Finance"],
        responses={200: "Settlement summary"},
    )
    @action(detail=False, methods=["get"])
    def settlements(self, request):
        settlements = Payment.objects.values("vendor__store_name").annotate(total_paid=models.Sum("amount"))
        return Response({"success": True, "data": settlements})
    

    @swagger_auto_schema(
        operation_summary="Get settlements for a specific vendor",
        tags=["Finance"],
        manual_parameters=[openapi.Parameter("vendor_id", openapi.IN_PATH, description="Vendor ID", type=openapi.TYPE_INTEGER)],
        responses={200: "Vendor settlement details"}
    )
    @action(detail=True, methods=["get"])
    def vendor_settlements(self, request, pk=None):
        try:
            vendor = Vendor.objects.get(pk=pk)
            settlements = Payment.objects.filter(vendor=vendor).aggregate(total_paid=models.Sum("amount"))
            return Response({"success": True, "data": settlements})
        except Vendor.DoesNotExist:
            return Response({"success": False, "message": "Vendor not found"}, status=404)



    @swagger_auto_schema(
        operation_summary="Admin sales & orders analytics",
        tags=["Analytics"],
        responses={200: "Sales analytics"}
    )
    @action(detail=False, methods=["get"])
    def analytics(self, request):
        data = {
            "total_orders": Order.objects.count(),
            "total_revenue": Payment.objects.aggregate(total=models.Sum("amount"))["total"],
            "pending_orders": Order.objects.filter(status="pending").count(),
            "delivered_orders": Order.objects.filter(status="delivered").count(),
        }
        return Response({"success": True, "data": data})
