import logging
import json
import base64
import os
from django.core.files.base import ContentFile
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.contrib.auth.password_validation import validate_password, ValidationError

from authentication.models import CustomUser
from users.models import Customer, Vendor, BusinessAdmin
from users.serializers import (
    CustomerProfileSerializer,
    CustomerProfileUpdateSerializer,
    VendorProfileSerializer,
    VendorProfileUpdateSerializer,
    BusinessAdminProfileSerializer
)
from authentication.models import CustomUser



logger = logging.getLogger(__name__)

class ProfileService:
    """Generic service for profile operations for all roles."""

    # ---------------------------
    # GET PROFILE
    # ---------------------------
    @staticmethod
    def get_profile(user, request=None):
        """
        Returns serialized profile data based on user role.
        """
        if not user:
            return None

        context = {"request": request} if request else {}

        if user.role == CustomUser.Role.VENDOR and hasattr(user, "vendor_profile"):
            return VendorProfileSerializer(
                user.vendor_profile,
                context=context
            ).data

        if user.role == CustomUser.Role.CUSTOMER and hasattr(user, "customer_profile"):
            return CustomerProfileSerializer(
                user.customer_profile,
                context=context
            ).data

        if user.role == CustomUser.Role.BUSINESS_ADMIN and hasattr(user, "business_admin_profile"):
            return BusinessAdminProfileSerializer(
                user.business_admin_profile,
                context=context
            ).data

        return None

    # ---------------------------
    # UPDATE PROFILE
    # ---------------------------
    @staticmethod
    @transaction.atomic
    def update_profile(user, data=None, files=None, request=None, partial=True):
        if not user:
            raise PermissionDenied("Authentication required")

        try:
            context = {'request': request} if request else {}

            # Ensure data is a dict
            if data is None:
                data = {}
            
            # Handle profile picture
            if files and 'profile_picture' in files:
                ProfileService._process_profile_picture_file(user, files['profile_picture'])
            elif data and 'image_data' in data:
                ProfileService._process_image_data(user, data.get('image_data'))

            # Handle password change
            if data and 'current_password' in data and 'new_password' in data:
                result = ProfileService.process_password_change(user, data['current_password'], data['new_password'])
                if not result.get('success'):
                    return False, {"success": False, "error": result.get('error')}, 400

            # Restrict fields per role
            restricted_fields = ['uuid', 'email', 'role', 'is_superuser', 'is_staff']
            safe_data = {k: v for k, v in data.items() if k not in restricted_fields + ['profile_picture', 'image_data', 'current_password', 'new_password']}

            # Choose serializer based on role
            if user.is_customer:
                profile = Customer.objects.get(user=user)
                serializer = CustomerProfileUpdateSerializer(profile, data=safe_data, partial=partial, context=context)
            elif user.is_vendor:
                profile = Vendor.objects.get(user=user)
                serializer = VendorProfileUpdateSerializer(profile, data=safe_data, partial=partial, context=context)
            else:  # Admin
                serializer = BusinessAdminProfileSerializer(user, data=safe_data, partial=partial, context=context)

            if not serializer.is_valid():
                logger.error(f"Profile serializer validation failed for {user.email}: {serializer.errors}")
                return False, {"success": False, "error": serializer.errors}, 400

            serializer.save()
            
            # Update base user fields
            base_fields = ['full_name', 'phone_number']
            update_fields = []
            for field in base_fields:
                if field in data:
                    setattr(user, field, data[field])
                    update_fields.append(field)
            if update_fields:
                user.save(update_fields=update_fields)

            updated_data = ProfileService.get_profile(user, request=request)
            logger.info(f"Profile updated for {user.email}")
            return True, {"success": True, "data": updated_data, "message": "Profile updated successfully"}, 200

        except Exception as e:
            logger.error(f"Error updating profile for {user.email}: {str(e)}", exc_info=True)
            return False, {"success": False, "error": "An error occurred while updating profile"}, 500

    # ---------------------------
    # PASSWORD CHANGE
    # ---------------------------
    @staticmethod
    def process_password_change(user, current_password, new_password):
        if not user.check_password(current_password):
            return {'success': False, 'error': "Current password is incorrect"}
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return {'success': False, 'error': ', '.join(e.messages)}

        user.set_password(new_password)
        user.save(update_fields=['password'])
        # Optional: blacklist tokens if using JWT
        logger.info(f"Password changed for {user.email}")
        return {'success': True, 'message': 'Password updated successfully'}

    # ---------------------------
    # IMAGE HANDLING
    # ---------------------------
    @staticmethod
    def _process_image_data(user, image_data):
        if not image_data:
            return

        try:
            data_url = image_data if ';base64' in image_data else f"data:image/jpeg;base64,{image_data}"
            format_part, imgstr = data_url.split(';base64')
            ext = format_part.split('/')[-1].lower()
            if ext not in ['jpeg', 'jpg', 'png', 'gif', 'webp']:
                ext = 'jpeg'

            file_data = ContentFile(
                base64.b64decode(imgstr),
                name=f"profile_{str(user.uuid)}.{ext}"
            )

            user.profile_picture = file_data
            user.save(update_fields=['profile_picture'])

            logger.info(f"Profile picture updated for {user.email}")

        except Exception as e:
            logger.error(f"Error updating profile picture: {str(e)}")
            raise


    @staticmethod
    def _process_profile_picture_file(user, file):
        """Save uploaded file as profile picture"""
        user.profile_picture = file
        user.save(update_fields=['profile_picture'])
        logger.info(f"Profile picture updated for {user.email}")



class AdminService:
    @staticmethod
    def update_product(slug, data):
        from store.models import Product
        from store.serializers import ProductSerializer
        
        try:
            product = Product.objects.get(slug=slug)
        except Product.DoesNotExist:
            return False, {"error": "Product not found"}

        serializer = ProductSerializer(product, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return True, serializer.data
        else:
            return False, serializer.errors
