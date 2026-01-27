"""
Tests for ProfileResolver to ensure all user types work correctly.
This test suite ensures that the ProfileResolver handles missing profiles gracefully
and doesn't break access for any user type.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from users.models import Customer, Vendor, BusinessAdmin
from users.services.profile_resolver import ProfileResolver

User = get_user_model()


class ProfileResolverTestCase(TestCase):
    """Test ProfileResolver for all user types"""

    def setUp(self):
        """Set up test users for each role"""
        # Create a customer user
        self.customer_user = User.objects.create_user(
            email='customer@test.com',
            password='testpass123',
            role=User.Role.CUSTOMER,
            full_name='Test Customer'
        )
        
        # Create a vendor user
        self.vendor_user = User.objects.create_user(
            email='vendor@test.com',
            password='testpass123',
            role=User.Role.VENDOR,
            full_name='Test Vendor'
        )
        
        # Create a business admin user
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            role=User.Role.BUSINESS_ADMIN,
            full_name='Test Admin'
        )

    def test_customer_profile_resolution_with_profile(self):
        """Test that customer profile is returned when it exists"""
        customer_profile = ProfileResolver.resolve_customer(self.customer_user)
        self.assertIsNotNone(customer_profile)
        self.assertIsInstance(customer_profile, Customer)
        self.assertEqual(customer_profile.user, self.customer_user)

    def test_customer_profile_resolution_creates_missing_profile(self):
        """Test that customer profile is created if missing but user has CUSTOMER role"""
        # Delete the customer profile to simulate a missing profile
        Customer.objects.filter(user=self.customer_user).delete()
        
        # Verify profile is missing
        self.assertFalse(hasattr(self.customer_user, 'customer_profile'))
        
        # Resolve should create the profile
        customer_profile = ProfileResolver.resolve_customer(self.customer_user)
        self.assertIsNotNone(customer_profile)
        self.assertIsInstance(customer_profile, Customer)

    def test_vendor_profile_resolution_with_profile(self):
        """Test that vendor profile is returned when it exists"""
        vendor_profile = ProfileResolver.resolve_vendor(self.vendor_user)
        self.assertIsNotNone(vendor_profile)
        self.assertIsInstance(vendor_profile, Vendor)
        self.assertEqual(vendor_profile.user, self.vendor_user)

    def test_vendor_profile_resolution_creates_missing_profile(self):
        """Test that vendor profile is created if missing but user has VENDOR role"""
        # Delete the vendor profile to simulate a missing profile
        Vendor.objects.filter(user=self.vendor_user).delete()
        
        # Verify profile is missing
        self.assertFalse(hasattr(self.vendor_user, 'vendor_profile'))
        
        # Resolve should create the profile
        vendor_profile = ProfileResolver.resolve_vendor(self.vendor_user)
        self.assertIsNotNone(vendor_profile)
        self.assertIsInstance(vendor_profile, Vendor)

    def test_admin_profile_resolution_with_profile(self):
        """Test that admin profile is returned when it exists"""
        admin_profile = ProfileResolver.resolve_admin(self.admin_user)
        self.assertIsNotNone(admin_profile)
        self.assertIsInstance(admin_profile, BusinessAdmin)
        self.assertEqual(admin_profile.user, self.admin_user)

    def test_admin_profile_resolution_creates_missing_profile(self):
        """Test that admin profile is created if missing but user has BUSINESS_ADMIN role"""
        # Delete the admin profile to simulate a missing profile
        BusinessAdmin.objects.filter(user=self.admin_user).delete()
        
        # Verify profile is missing
        self.assertFalse(hasattr(self.admin_user, 'business_admin_profile'))
        
        # Resolve should create the profile
        admin_profile = ProfileResolver.resolve_admin(self.admin_user)
        self.assertIsNotNone(admin_profile)
        self.assertIsInstance(admin_profile, BusinessAdmin)

    def test_customer_cannot_access_vendor_profile(self):
        """Test that a customer user cannot resolve a vendor profile"""
        vendor_profile = ProfileResolver.resolve_vendor(self.customer_user)
        self.assertIsNone(vendor_profile)

    def test_vendor_cannot_access_customer_profile(self):
        """Test that a vendor user cannot resolve a customer profile"""
        # But they DO have a customer profile since signal should have created it if role is CUSTOMER
        # So we test that vendor role doesn't match customer check
        vendor_user = User.objects.create_user(
            email='onlyvendor@test.com',
            password='testpass123',
            role=User.Role.VENDOR,
            full_name='Only Vendor'
        )
        customer_profile = ProfileResolver.resolve_customer(vendor_user)
        self.assertIsNone(customer_profile)

    def test_admin_cannot_access_customer_profile(self):
        """Test that an admin user cannot resolve a customer profile"""
        customer_profile = ProfileResolver.resolve_customer(self.admin_user)
        self.assertIsNone(customer_profile)

    def test_admin_cannot_access_vendor_profile(self):
        """Test that an admin user cannot resolve a vendor profile"""
        vendor_profile = ProfileResolver.resolve_vendor(self.admin_user)
        self.assertIsNone(vendor_profile)
