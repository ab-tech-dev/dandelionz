from users.models import Vendor, Customer, BusinessAdmin
from django.contrib.auth import get_user_model

User = get_user_model()


class ProfileResolver:

    @staticmethod
    def resolve_customer(user):
        if user.role != User.Role.CUSTOMER:
            return None
        return getattr(user, "customer_profile", None)

    @staticmethod
    def resolve_vendor(user):
        if user.role != User.Role.VENDOR:
            return None
        return getattr(user, "vendor_profile", None)

    @staticmethod
    def resolve_admin(user):
        if user.role != User.Role.BUSINESS_ADMIN:
            return None
        return getattr(user, "business_admin_profile", None)
