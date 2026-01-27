from users.models import Vendor, Customer, BusinessAdmin
from django.contrib.auth import get_user_model

User = get_user_model()


class ProfileResolver:

    @staticmethod
    def resolve_customer(user):
        # Check if customer profile exists (most reliable way to determine if user is a customer)
        customer_profile = getattr(user, "customer_profile", None)
        if customer_profile:
            return customer_profile
        # Fallback to role check if profile doesn't exist
        if user.role == User.Role.CUSTOMER:
            # Try to create the profile if it's missing
            try:
                customer_profile, created = Customer.objects.get_or_create(user=user)
                return customer_profile
            except Exception:
                pass
        return None

    @staticmethod
    def resolve_vendor(user):
        # Check if vendor profile exists (most reliable way to determine if user is a vendor)
        vendor_profile = getattr(user, "vendor_profile", None)
        if vendor_profile:
            return vendor_profile
        # Fallback to role check if profile doesn't exist
        if user.role == User.Role.VENDOR:
            # Try to create the profile if it's missing
            try:
                vendor_profile, created = Vendor.objects.get_or_create(
                    user=user,
                    defaults={
                        "store_name": "Unnamed Store",
                        "is_verified_vendor": False
                    }
                )
                return vendor_profile
            except Exception:
                pass
        return None

    @staticmethod
    def resolve_admin(user):
        # Check if admin profile exists (most reliable way to determine if user is a business admin)
        admin_profile = getattr(user, "business_admin_profile", None)
        if admin_profile:
            return admin_profile
        # Fallback to role check if profile doesn't exist
        if user.role == User.Role.BUSINESS_ADMIN:
            # Try to create the profile if it's missing
            try:
                admin_profile, created = BusinessAdmin.objects.get_or_create(user=user)
                return admin_profile
            except Exception:
                pass
        return None
