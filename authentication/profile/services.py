import base64
import json
import logging
import os
from django.core.files.base import ContentFile
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction

from authentication.core.jwt_utils import TokenManager
from authentication.models import CustomUser, Vendor, Customer
from authentication.serializers import (
    VendorProfileSerializer,
    CustomerProfileSerializer,
    AdminProfileSerializer
)

logger = logging.getLogger(__name__)


class ProfileService:
    """Service class to handle user profile operations (role-aware)"""

    # ==============================================================
    # GET PROFILE
    # ==============================================================
    @staticmethod
    def get_profile(user=None, request=None):
        """
        Retrieve user profile data based on role.
        Automatically detects authenticated user if not explicitly provided.
        """
        if not user:
            if request and hasattr(request, "user") and request.user.is_authenticated:
                user = request.user
            else:
                logger.warning("Attempt to access profile without authentication")
                raise PermissionDenied("Authentication required")

        context = {'request': request} if request else {}

        # Return role-based profile serializer
        if user.role == CustomUser.Role.VENDOR:
            profile = Vendor.objects.get(user=user)
            serializer = VendorProfileSerializer(profile, context=context)
        elif user.role == CustomUser.Role.CUSTOMER:
            profile = Customer.objects.get(user=user)
            serializer = CustomerProfileSerializer(profile, context=context)
        else:
            serializer = AdminProfileSerializer(user, context=context)

        logger.info(f"Profile retrieved for {user.email} ({user.role})")
        return serializer.data


    # ==============================================================
    # UPDATE PROFILE
    # ==============================================================
    @staticmethod
    @transaction.atomic
    def update_profile(user=None, data=None, files=None, request=None):
        """
        Update user profile data with support for:
        - role-based profile updates
        - password changes
        - image uploads or base64 image data
        """
        try:
            if not user:
                if request and hasattr(request, "user") and request.user.is_authenticated:
                    user = request.user
                else:
                    logger.warning("Anonymous user attempted to update profile")
                    raise PermissionDenied("Authentication required to update profile")

            # Handle profile picture (file or base64 data)
            if files and 'profile_picture' in files:
                ProfileService._process_profile_picture_file(user, files['profile_picture'])
            elif 'image_data' in data:
                ProfileService._process_image_data(user, data.get('image_data'))

            # Handle password change
            if 'current_password' in data and 'new_password' in data:
                result = ProfileService.process_password_change(
                    user,
                    data.get('current_password'),
                    data.get('new_password')
                )

                if not result.get('success'):
                    return False, result, 400

            # Restrict sensitive fields
            restricted_fields = [
                'is_superuser', 'is_staff', 'balance',
                'wallet', 'email_verified', 'role', 'id', 'email'
            ]
            safe_data = {
                k: v for k, v in data.items()
                if k not in ['profile_picture', 'image_data', 'current_password', 'new_password'] + restricted_fields
            }

            context = {'request': request} if request else {}

            # Choose serializer based on role
            if user.role == CustomUser.Role.VENDOR:
                profile = Vendor.objects.get(user=user)
                serializer = VendorProfileSerializer(profile, data=safe_data, partial=True, context=context)
            elif user.role == CustomUser.Role.CUSTOMER:
                profile = Customer.objects.get(user=user)
                serializer = CustomerProfileSerializer(profile, data=safe_data, partial=True, context=context)
            else:
                serializer = AdminProfileSerializer(user, data=safe_data, partial=True, context=context)

            if serializer.is_valid():
                serializer.save()

                # Update main user fields if any base fields exist (e.g. full_name, phone_number)
                user_fields = ['full_name', 'phone_number']
                user_update_data = {field: data[field] for field in user_fields if field in data}
                if user_update_data:
                    for field, value in user_update_data.items():
                        setattr(user, field, value)
                    user.save(update_fields=list(user_update_data.keys()))

                updated_data = ProfileService.get_profile(user=user, request=request)
                ProfileService._log_profile_update(user, safe_data)

                logger.info(f"Profile successfully updated for {user.email}")
                return True, {
                    "success": True,
                    "data": updated_data,
                    "message": "Profile updated successfully"
                }, 200

            return False, {
                "success": False,
                "error": serializer.errors
            }, 400

        except Exception as e:
            logger.error(f"Profile update error for user {user.email if user else 'unknown'}: {str(e)}", exc_info=True)
            return False, {
                "success": False,
                "error": "Failed to update profile"
            }, 400


    # ==============================================================
    # PASSWORD CHANGE
    # ==============================================================
    @staticmethod
    def process_password_change(user, current_password, new_password):
        """Handle password change securely with validation and token revocation"""
        if not user.check_password(current_password):
            return {'success': False, 'error': "Current password is incorrect"}

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return {'success': False, 'error': ', '.join(e.messages)}

        user.set_password(new_password)
        user.save(update_fields=['password'])
        TokenManager.blacklist_all_user_tokens(user.id)

        logger.info(f"Password successfully changed for {user.email}")
        return {'success': True, 'message': 'Password updated successfully'}


    # ==============================================================
    # IMAGE PROCESSING (Base64 and File)
    # ==============================================================
    @staticmethod
    def _process_image_data(user, image_data):
        """Decode and save base64 image data to user profile"""
        try:
            try:
                image_list = json.loads(image_data)
                if isinstance(image_list, list) and len(image_list) > 0:
                    image_info = image_list[0]
                    data_url = image_info.get('data')
                else:
                    data_url = f"data:image/jpeg;base64,{image_data}"
            except json.JSONDecodeError:
                data_url = f"data:image/jpeg;base64,{image_data}"

            if ';base64' not in data_url:
                raise ValueError("Invalid image data format - missing base64 prefix")

            format_part, imgstr = data_url.split(';base64')
            ext = format_part.split('/')[-1].lower() if '/' in format_part else 'jpeg'
            if ext not in ['jpeg', 'jpg', 'png', 'gif', 'webp']:
                ext = 'jpeg'

            data = ContentFile(base64.b64decode(imgstr), name=f"profile_{user.id}.{ext}")

            # Remove old image if exists
            if user.profile_picture and os.path.isfile(user.profile_picture.path):
                os.remove(user.profile_picture.path)

            user.profile_picture = data
            user.save(update_fields=['profile_picture'])
            logger.info(f"Profile picture updated from base64 for {user.email}")
            return True

        except Exception as e:
            logger.error(f"Error processing image data for {user.email}: {str(e)}", exc_info=True)
            raise


    @staticmethod
    def _process_profile_picture_file(user, file):
        """Save uploaded profile picture file safely"""
        try:
            if user.profile_picture and os.path.isfile(user.profile_picture.path):
                os.remove(user.profile_picture.path)
        except (ValueError, OSError) as e:
            logger.warning(f"Could not remove old profile picture for {user.email}: {e}")

        user.profile_picture = file
        user.save(update_fields=['profile_picture'])
        logger.info(f"Profile picture updated for {user.email}")
        return True


    # ==============================================================
    # AUDIT TRAIL
    # ==============================================================
    @staticmethod
    def _log_profile_update(user, updated_data):
        """Log profile updates for security/audit tracking"""
        masked_data = {k: ('****' if 'password' in k else v) for k, v in updated_data.items()}
        logger.info(f"Audit: Profile updated for {user.email} with data: {masked_data}")
