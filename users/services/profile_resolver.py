from django.contrib.auth import get_user_model
from users.models import Customer, BusinessAdmin, Vendor

User = get_user_model()


class ProfileResolver:
    @staticmethod
    def get_vendor(user):
        if user.role != User.Role.VENDOR:
            return None

        vendor, _ = Vendor.objects.get_or_create(
            user=user,
            defaults={
                "store_name": user.full_name or "Unnamed Store"
            }
        )
        return vendor

    @staticmethod
    def get_customer(user):
        if user.role != User.Role.CUSTOMER:
            return None

        customer, _ = Customer.objects.get_or_create(user=user)
        return customer

    @staticmethod
    def get_business_admin(user):
        if user.role != User.Role.BUSINESS_ADMIN:
            return None

        admin, _ = BusinessAdmin.objects.get_or_create(user=user)
        return admin
