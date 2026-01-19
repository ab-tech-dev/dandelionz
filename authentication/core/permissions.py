from rest_framework.permissions import BasePermission, SAFE_METHODS

# =====================================================
# Generic Role Permissions
# =====================================================

class IsAdmin(BasePermission):
    """
    Allows access only to users with role ADMIN or BUSINESS_ADMIN
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Allow if user is main admin
        if request.user.is_admin:
            return True
        # Allow if user is business admin
        if hasattr(request.user, 'business_admin_profile'):
            return True
        return False


class IsBusinessAdmin(BasePermission):
    """
    Allows access only to authenticated users with BUSINESS_ADMIN role.
    Used for strict admin dashboard access control.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.is_business_admin or request.user.is_admin


class IsVendor(BasePermission):
    """
    Allows access only to users with role VENDOR
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_vendor


class IsCustomer(BasePermission):
    """
    Allows access only to users with role CUSTOMER
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_customer


class IsDeliveryAgent(BasePermission):
    """
    Allows access only to users with role DELIVERY_AGENT
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return hasattr(request.user, 'deliveryagent')


# =====================================================
# Mixed Permissions
# =====================================================

class IsAdminOrVendor(BasePermission):
    """
    Access allowed if user is ADMIN or VENDOR
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_admin or request.user.is_vendor)


class IsAdminOrCustomer(BasePermission):
    """
    Access allowed if user is ADMIN or CUSTOMER
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_admin or request.user.is_customer)


class IsVendorOrCustomer(BasePermission):
    """
    Access allowed if user is VENDOR or CUSTOMER
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_vendor or request.user.is_customer)


# =====================================================
# Read-Only Permission for Certain Roles
# =====================================================

class ReadOnly(BasePermission):
    """
    Grants read-only access (GET, HEAD, OPTIONS)
    """
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class IsAdminReadOnlyOrVendorWrite(BasePermission):
    """
    Admins have full access; Vendors can only write
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_admin:
            return True
        if request.user.is_vendor and request.method not in SAFE_METHODS:
            return True
        return False
