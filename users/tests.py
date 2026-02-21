from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from users.models import BusinessAdmin, Vendor


class AdminVendorApprovalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client = APIClient()

        self.admin_user = User.objects.create_user(
            email="admin@test.com",
            password="pass12345",
            role=User.Role.BUSINESS_ADMIN,
            is_staff=True,
        )
        BusinessAdmin.objects.get_or_create(user=self.admin_user)
        self.client.force_authenticate(user=self.admin_user)

        # Simulate existing vendor profile attached to a non-vendor role user.
        self.vendor_user = User.objects.create_user(
            email="vendor_candidate@test.com",
            password="pass12345",
            role=User.Role.CUSTOMER,
            is_verified=False,
        )
        self.vendor_profile = Vendor.objects.create(
            user=self.vendor_user,
            store_name="Candidate Store",
            is_verified_vendor=False,
            vendor_status="pending",
        )

    @patch("users.views.send_user_notification")
    def test_approve_vendor_persists_is_active_and_user_role(self, mock_send_user_notification):
        response = self.client.post(
            "/user/admin/vendors/approve/",
            {"user_uuid": str(self.vendor_user.uuid), "approve": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["approved"])

        self.vendor_user.refresh_from_db()
        self.vendor_profile.refresh_from_db()

        self.assertEqual(self.vendor_user.role, self.vendor_user.Role.VENDOR)
        self.assertTrue(self.vendor_user.is_active)
        self.assertFalse(self.vendor_profile.is_verified_vendor)
        self.assertEqual(self.vendor_profile.vendor_status, "approved")
        mock_send_user_notification.assert_called_once()

    @patch("users.views.send_user_notification")
    def test_verify_kyc_can_approve_and_reject_using_is_verified_vendor(self, mock_send_user_notification):
        approve_response = self.client.post(
            "/user/admin/vendors/verify-kyc/",
            {"user_uuid": str(self.vendor_user.uuid), "approve": True},
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertTrue(approve_response.data["success"])
        self.assertTrue(approve_response.data["approved"])

        self.vendor_profile.refresh_from_db()
        self.assertTrue(self.vendor_profile.is_verified_vendor)

        reject_response = self.client.post(
            "/user/admin/vendors/verify-kyc/",
            {"user_uuid": str(self.vendor_user.uuid), "approve": False},
            format="json",
        )
        self.assertEqual(reject_response.status_code, status.HTTP_200_OK)
        self.assertTrue(reject_response.data["success"])
        self.assertFalse(reject_response.data["approved"])

        self.vendor_profile.refresh_from_db()
        self.assertFalse(self.vendor_profile.is_verified_vendor)
        self.assertEqual(mock_send_user_notification.call_count, 2)
