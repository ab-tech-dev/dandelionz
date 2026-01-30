"""
Tests for profile image upload with base64 encoding
"""
from django.test import TestCase
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from users.models import Customer
import base64
from PIL import Image
import io

User = get_user_model()


class Base64ImageUploadTestCase(APITestCase):
    """Test base64 image upload for customer profile"""

    def setUp(self):
        """Create test user and customer"""
        self.client = APIClient()
        
        # Create test user
        self.user = User.objects.create_user(
            email='testcustomer@example.com',
            password='testpass123',
            full_name='Test Customer',
            role=User.Role.CUSTOMER
        )
        
        # Create customer profile
        self.customer = Customer.objects.create(
            user=self.user,
            shipping_address='123 Test St',
            city='Test City',
            country='Test Country',
            postal_code='12345'
        )
        
        self.client.force_authenticate(user=self.user)

    def create_test_image_base64(self, format='jpeg', size=(100, 100)):
        """Create a test image and return base64 encoded data"""
        image = Image.new('RGB', size, color='red')
        image_io = io.BytesIO()
        image.save(image_io, format=format.upper())
        image_io.seek(0)
        image_data = image_io.read()
        
        # Encode to base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # Return as data URL
        return f'data:image/{format};base64,{base64_data}'

    def test_profile_patch_with_base64_image(self):
        """Test PATCH profile endpoint with base64 encoded image"""
        base64_image = self.create_test_image_base64()
        
        payload = {
            'full_name': 'Updated Name',
            'profile_picture': base64_image,
            'phone_number': '1234567890'
        }
        
        response = self.client.patch(
            '/api/customer/profile/',
            payload,
            format='json'
        )
        
        # Should return 200 OK
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify the data
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['full_name'], 'Updated Name')
        self.assertEqual(response.data['user']['phone_number'], '1234567890')
        
        # Verify profile_picture was updated (should be a Cloudinary ID)
        self.assertIn('profile_picture', response.data['user'])
        self.assertIsNotNone(response.data['user']['profile_picture'])

    def test_profile_patch_with_plain_base64_image(self):
        """Test PATCH with plain base64 (no data URL prefix)"""
        image = Image.new('RGB', (100, 100), color='blue')
        image_io = io.BytesIO()
        image.save(image_io, format='PNG')
        image_io.seek(0)
        
        base64_data = base64.b64encode(image_io.read()).decode('utf-8')
        
        payload = {
            'profile_picture': base64_data,
        }
        
        response = self.client.patch(
            '/api/customer/profile/',
            payload,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('profile_picture', response.data['user'])

    def test_profile_patch_with_invalid_base64(self):
        """Test PATCH with invalid base64 image"""
        payload = {
            'profile_picture': 'not-valid-base64!!!',
        }
        
        response = self.client.patch(
            '/api/customer/profile/',
            payload,
            format='json'
        )
        
        # Should return 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_patch_without_image(self):
        """Test PATCH without image (should not fail)"""
        payload = {
            'full_name': 'Updated Name',
            'phone_number': '9876543210'
        }
        
        response = self.client.patch(
            '/api/customer/profile/',
            payload,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['full_name'], 'Updated Name')

    def test_profile_patch_with_empty_image(self):
        """Test PATCH with empty/null image"""
        payload = {
            'profile_picture': None,
            'full_name': 'Another Update'
        }
        
        response = self.client.patch(
            '/api/customer/profile/',
            payload,
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['full_name'], 'Another Update')

    def test_unauthenticated_profile_patch(self):
        """Test PATCH without authentication"""
        self.client.force_authenticate(user=None)
        
        payload = {
            'full_name': 'Updated Name',
        }
        
        response = self.client.patch(
            '/api/customer/profile/',
            payload,
            format='json'
        )
        
        # Should return 401 Unauthorized
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
