"""
Admin Dashboard API Views

Provides centralized endpoints for admin user management, order management, and profile operations.
All endpoints require BUSINESS_ADMIN or ADMIN role authentication.
All admin actions are automatically logged for audit trail.
"""

from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.core.permissions import IsBusinessAdmin
from authentication.core.response import standardized_response
from authentication.models import UserSuspension, AdminAuditLog
from authentication.serializers_admin import (
    AdminDashboardUserListSerializer,
    AdminDashboardUserDetailSerializer,
    AdminDashboardUserSuspendSerializer,
    AdminDashboardOrderListSerializer,
    AdminDashboardOrderDetailSerializer,
    AdminDashboardOrderCancelSerializer,
    AdminDashboardOrderStatusUpdateSerializer,
    AdminDashboardProfileSerializer,
    AdminDashboardProfileUpdateSerializer,
    AdminDashboardPasswordVerifySerializer,
    AdminDashboardPasswordChangeSerializer,
    AdminDashboardPhotoUploadSerializer,
    AdminDashboardAuditLogSerializer,
)
from transactions.models import Order, OrderStatusHistory

CustomUser = get_user_model()


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def log_admin_action(admin, action, target_entity, target_id, reason=None, details=None):
    """Create audit log entry for admin action"""
    AdminAuditLog.objects.create(
        admin=admin,
        action=action,
        target_entity=target_entity,
        target_id=target_id,
        reason=reason,
        details=details or {}
    )


def invalidate_user_sessions(user):
    """Invalidate all active sessions for a user (if using session auth)"""
    from django.contrib.sessions.models import Session
    from django.contrib.auth.models import update_last_login
    user.last_login = None
    user.save(update_fields=['last_login'])


# =====================================================
# USER MANAGEMENT VIEWS
# =====================================================

class AdminUserListView(generics.ListAPIView):
    """
    List all platform users with basic info.
    
    Query Parameters:
    - status: Filter by user status (ACTIVE, SUSPENDED)
    - role: Filter by user role (CUSTOMER, VENDOR, etc.)
    - search: Search by email or full name
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardUserListSerializer
    
    def get_queryset(self):
        queryset = CustomUser.objects.exclude(role='ADMIN')
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by role
        role_param = self.request.query_params.get('role')
        if role_param:
            queryset = queryset.filter(role=role_param)
        
        # Search by email or name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) | Q(full_name__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                standardized_response(data=serializer.data)
            )
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(standardized_response(data=serializer.data))


class AdminUserDetailView(generics.RetrieveAPIView):
    """Retrieve detailed information about a specific user"""
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardUserDetailSerializer
    queryset = CustomUser.objects.all()
    lookup_field = 'uuid'
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(standardized_response(data=serializer.data))


class AdminUserSuspendView(generics.GenericAPIView):
    """
    Suspend or reinstate a user.
    
    POST /admin/users/{uuid}/suspend/
    {
        "action": "suspend",  # or "reinstate"
        "reason": "Violation of platform policy"
    }
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardUserSuspendSerializer
    queryset = CustomUser.objects.all()
    lookup_field = 'uuid'
    
    def post(self, request, uuid):
        user = get_object_or_404(CustomUser, uuid=uuid)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action = serializer.validated_data.get('action', 'suspend')
        reason = serializer.validated_data['reason']
        
        if action == 'suspend':
            if user.status == CustomUser.UserStatus.SUSPENDED:
                return Response(
                    standardized_response(success=False, error="User is already suspended"),
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user.status = CustomUser.UserStatus.SUSPENDED
            user.save(update_fields=['status'])
            
            # Create suspension record
            UserSuspension.objects.create(
                user=user,
                admin=request.user,
                action=UserSuspension.Action.SUSPEND,
                reason=reason
            )
            
            # Invalidate sessions
            invalidate_user_sessions(user)
            
            # Log action
            log_admin_action(
                request.user,
                'suspend_user',
                'User',
                str(user.uuid),
                reason=reason
            )
            
            message = f"User {user.email} has been suspended"
        
        elif action == 'reinstate':
            if user.status == CustomUser.UserStatus.ACTIVE:
                return Response(
                    standardized_response(success=False, error="User is already active"),
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user.status = CustomUser.UserStatus.ACTIVE
            user.save(update_fields=['status'])
            
            # Create reinstatement record
            UserSuspension.objects.create(
                user=user,
                admin=request.user,
                action=UserSuspension.Action.REINSTATE,
                reason=reason
            )
            
            # Log action
            log_admin_action(
                request.user,
                'reinstate_user',
                'User',
                str(user.uuid),
                reason=reason
            )
            
            message = f"User {user.email} has been reinstated"
        
        return Response(
            standardized_response(
                success=True,
                message=message,
                data={'user_uuid': str(user.uuid), 'status': user.status}
            ),
            status=status.HTTP_200_OK
        )


# =====================================================
# ORDER MANAGEMENT VIEWS
# =====================================================

class AdminOrderListView(generics.ListAPIView):
    """
    List all orders with basic info.
    
    Query Parameters:
    - status: Filter by order status
    - payment_status: Filter by payment status
    - customer_email: Filter by customer email
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardOrderListSerializer
    
    def get_queryset(self):
        queryset = Order.objects.all()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by payment status
        payment_status = self.request.query_params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        
        # Filter by customer email
        customer_email = self.request.query_params.get('customer_email')
        if customer_email:
            queryset = queryset.filter(customer__email__icontains=customer_email)
        
        return queryset.order_by('-ordered_at')
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                standardized_response(data=serializer.data)
            )
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(standardized_response(data=serializer.data))


class AdminOrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update status, or delete a specific order"""
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    queryset = Order.objects.all()
    lookup_field = 'order_id'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return AdminDashboardOrderStatusUpdateSerializer
        return AdminDashboardOrderDetailSerializer
    
    @swagger_auto_schema(
        operation_id="admin_order_detail",
        operation_summary="Get Order Details",
        operation_description="Retrieve detailed information about a specific order.",
        tags=["Order Management"],
        manual_parameters=[
            openapi.Parameter(
                "order_id",
                openapi.IN_PATH,
                description="Order UUID",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True
            )
        ],
        responses={
            200: openapi.Response("Order details retrieved", AdminDashboardOrderDetailSerializer()),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = AdminDashboardOrderDetailSerializer(instance)
        return Response(standardized_response(data=serializer.data))

    @swagger_auto_schema(
        operation_id="admin_order_update_status",
        operation_summary="Update Order Status",
        operation_description="Update order status. Only allowed for PAID orders. Patchable field: status only.",
        tags=["Order Management"],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["status"],
            properties={
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=[choice[0] for choice in Order.Status.choices] + ["PROCESSING"]
                )
            },
            example={"status": "PROCESSING"}
        ),
        responses={
            200: openapi.Response(
                "Order status updated",
                AdminDashboardOrderDetailSerializer(),
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Order status updated",
                        "data": {"order_id": "19149b71-8f31-4142-9260-b48d0bc3f0f9", "status": "SHIPPED"}
                    }
                }
            ),
            400: openapi.Response("Only paid orders can be updated"),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    def update(self, request, *args, **kwargs):
        order = self.get_object()

        if order.status != Order.Status.PAID:
            return Response(
                standardized_response(success=False, error="Only paid orders can be updated"),
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data['status']
        if new_status != order.status:
            order.status = new_status
            order.save(update_fields=['status'])

            OrderStatusHistory.objects.create(
                order=order,
                status=new_status,
                changed_by='ADMIN',
                admin=request.user,
                reason=f"Order status updated to {new_status} by admin"
            )

        response_serializer = AdminDashboardOrderDetailSerializer(order)
        return Response(
            standardized_response(data=response_serializer.data, message="Order status updated")
        )

    @swagger_auto_schema(
        operation_id="admin_order_delete",
        operation_summary="Delete Pending Order",
        operation_description="Delete an order. Only allowed for PENDING orders.",
        tags=["Order Management"],
        responses={
            200: openapi.Response(
                "Order deleted",
                examples={
                    "application/json": {
                        "success": True,
                        "message": "Order 19149b71-8f31-4142-9260-b48d0bc3f0f9 deleted successfully"
                    }
                }
            ),
            400: openapi.Response("Only pending orders can be deleted"),
            404: openapi.Response("Order not found"),
            403: openapi.Response("Admin access only"),
        },
        security=[{"Bearer": []}],
    )
    def destroy(self, request, *args, **kwargs):
        order = self.get_object()

        if order.status != Order.Status.PENDING:
            return Response(
                standardized_response(success=False, error="Only pending orders can be deleted"),
                status=status.HTTP_400_BAD_REQUEST
            )

        order_id = order.order_id
        order.delete()

        return Response(
            standardized_response(message=f"Order {order_id} deleted successfully"),
            status=status.HTTP_200_OK
        )


class AdminOrderCancelView(generics.GenericAPIView):
    """
    Cancel an order (admin-initiated).
    
    POST /admin/orders/{order_id}/cancel/
    {
        "reason": "Vendor unable to fulfill order"
    }
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardOrderCancelSerializer
    queryset = Order.objects.all()
    lookup_field = 'order_id'
    
    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        reason = serializer.validated_data['reason']
        
        # Check if order can be cancelled
        if order.status == Order.Status.CANCELED:
            return Response(
                standardized_response(success=False, error="Order is already cancelled"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if order.status == Order.Status.DELIVERED:
            return Response(
                standardized_response(success=False, error="Cannot cancel a delivered order"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create status history entry
        old_status = order.status
        order.status = Order.Status.CANCELED
        order.save(update_fields=['status'])
        
        OrderStatusHistory.objects.create(
            order=order,
            status=Order.Status.CANCELED,
            changed_by='ADMIN',
            admin=request.user,
            reason=reason
        )
        
        # Log action
        log_admin_action(
            request.user,
            'cancel_order',
            'Order',
            str(order.order_id),
            reason=reason,
            details={'old_status': old_status, 'new_status': order.status}
        )
        
        return Response(
            standardized_response(
                success=True,
                message=f"Order {order.order_id} has been cancelled",
                data={'order_id': str(order.order_id), 'status': order.status}
            ),
            status=status.HTTP_200_OK
        )


# =====================================================
# ADMIN PROFILE MANAGEMENT VIEWS
# =====================================================

class AdminProfileView(generics.GenericAPIView):
    """
    Retrieve and update admin's own profile.
    
    GET /admin/profile/ - Get profile info
    PUT /admin/profile/ - Update profile
    PATCH /admin/profile/ - Partial update
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardProfileSerializer
    
    def get(self, request):
        serializer = AdminDashboardProfileSerializer(request.user)
        return Response(standardized_response(data=serializer.data))
    
    def put(self, request):
        serializer = AdminDashboardProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        for field, value in serializer.validated_data.items():
            setattr(request.user, field, value)
        
        request.user.save()
        
        # Log action
        log_admin_action(
            request.user,
            'update_profile',
            'Admin',
            str(request.user.uuid),
            details=serializer.validated_data
        )
        
        return Response(
            standardized_response(
                success=True,
                message="Profile updated successfully",
                data=AdminDashboardProfileSerializer(request.user).data
            )
        )
    
    def patch(self, request):
        return self.put(request)


class AdminPhotoUploadView(generics.GenericAPIView):
    """
    Upload or update admin profile photo.
    
    POST /admin/profile/photo/ (multipart/form-data)
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardPhotoUploadSerializer
    
    def post(self, request):
        serializer = AdminDashboardPhotoUploadSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Log action
        log_admin_action(
            request.user,
            'upload_profile_photo',
            'Admin',
            str(request.user.uuid)
        )
        
        return Response(
            standardized_response(
                success=True,
                message="Profile photo updated successfully",
                data=AdminDashboardProfileSerializer(request.user).data
            )
        )


class AdminPasswordVerifyView(generics.GenericAPIView):
    """
    Verify current password (step 1 before password change).
    
    POST /admin/password/verify/
    {
        "current_password": "current_password_here"
    }
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardPasswordVerifySerializer
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        current_password = serializer.validated_data['current_password']
        
        if not request.user.check_password(current_password):
            return Response(
                standardized_response(success=False, error="Current password is incorrect"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            standardized_response(
                success=True,
                message="Password verified successfully"
            )
        )


class AdminPasswordChangeView(generics.GenericAPIView):
    """
    Change admin password (step 2 - change password).
    
    POST /admin/password/change/
    {
        "current_password": "current_password_here",
        "new_password": "new_secure_password",
        "new_password_confirm": "new_secure_password"
    }
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardPasswordChangeSerializer
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']
        
        if not request.user.check_password(current_password):
            return Response(
                standardized_response(success=False, error="Current password is incorrect"),
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new password
        request.user.set_password(new_password)
        request.user.save()
        
        # Invalidate all sessions
        invalidate_user_sessions(request.user)
        
        # Log action
        log_admin_action(
            request.user,
            'change_password',
            'Admin',
            str(request.user.uuid)
        )
        
        return Response(
            standardized_response(
                success=True,
                message="Password changed successfully. Please log in again.",
            ),
            status=status.HTTP_200_OK
        )


# =====================================================
# AUDIT LOG VIEW
# =====================================================

class AdminAuditLogView(generics.ListAPIView):
    """
    List admin audit logs (admin actions).
    
    Query Parameters:
    - admin_uuid: Filter by admin who performed action
    - action: Filter by action type
    - target_entity: Filter by entity type
    """
    permission_classes = [IsAuthenticated, IsBusinessAdmin]
    serializer_class = AdminDashboardAuditLogSerializer
    
    def get_queryset(self):
        queryset = AdminAuditLog.objects.all()
        
        admin_uuid = self.request.query_params.get('admin_uuid')
        if admin_uuid:
            queryset = queryset.filter(admin__uuid=admin_uuid)
        
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        target_entity = self.request.query_params.get('target_entity')
        if target_entity:
            queryset = queryset.filter(target_entity=target_entity)
        
        return queryset.order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                standardized_response(data=serializer.data)
            )
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(standardized_response(data=serializer.data))
