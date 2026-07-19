from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class RoleEndpointContractTests(TestCase):
    """
    Table-driven guard against the bug class that actually cost days on this
    project: a wrong-role user hitting an endpoint and getting the wrong status
    code instead of a clean 403. Each user is created with only a role — profile
    creation is left to the users.signals post_save handler (or, for ADMIN,
    deliberately left absent) rather than created explicitly here, since an
    explicit Vendor/Customer/BusinessAdmin.objects.create() in setUp collides
    with that signal (see users/test_role_endpoint_contracts collision notes
    in the ADMIN cases below, and the wider migration/signal write-up in
    project memory).
    """

    CASES = [
        # (role, method, path, expected_status)
        (User.Role.CUSTOMER, "get", "/user/customer/profile/", status.HTTP_200_OK),
        (User.Role.BUSINESS_ADMIN, "get", "/user/customer/profile/", status.HTTP_403_FORBIDDEN),
        (User.Role.VENDOR, "get", "/user/customer/profile/", status.HTTP_403_FORBIDDEN),
        (User.Role.ADMIN, "get", "/user/customer/profile/", status.HTTP_403_FORBIDDEN),
        (User.Role.VENDOR, "get", "/user/vendor/profile/", status.HTTP_200_OK),
        (User.Role.CUSTOMER, "get", "/user/vendor/profile/", status.HTTP_403_FORBIDDEN),
        (User.Role.BUSINESS_ADMIN, "get", "/user/vendor/profile/", status.HTTP_403_FORBIDDEN),
        (User.Role.BUSINESS_ADMIN, "get", "/user/admin/products/", status.HTTP_200_OK),
        (User.Role.VENDOR, "get", "/user/admin/products/", status.HTTP_403_FORBIDDEN),
        (User.Role.CUSTOMER, "get", "/user/admin/products/", status.HTTP_403_FORBIDDEN),
        # ADMIN (superuser) is deliberately not BUSINESS_ADMIN: ProfileResolver.resolve_admin
        # only recognizes the BUSINESS_ADMIN role, so a plain ADMIN role gets 403 here too.
        # This looks surprising but is documented, current behavior, not a regression.
        (User.Role.ADMIN, "get", "/user/admin/products/", status.HTTP_403_FORBIDDEN),
    ]

    def _make_user(self, role, index):
        kwargs = dict(
            email=f"contract_{role.lower()}_{index}@test.com",
            password="pass12345",
        )
        if role == User.Role.ADMIN:
            return User.objects.create_superuser(**kwargs)
        return User.objects.create_user(role=role, **kwargs)

    def test_role_endpoint_matrix(self):
        client = APIClient()
        for index, (role, method, path, expected_status) in enumerate(self.CASES):
            with self.subTest(role=role, method=method, path=path):
                user = self._make_user(role, index)
                client.force_authenticate(user=user)
                response = getattr(client, method)(path, format="json")
                self.assertEqual(
                    response.status_code,
                    expected_status,
                    f"{role} {method.upper()} {path}: expected {expected_status}, "
                    f"got {response.status_code} ({getattr(response, 'data', None)})",
                )
                client.force_authenticate(user=None)