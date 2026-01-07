import logging
import traceback
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from authentication.verification.tokens import TokenVerifier
from authentication.core.jwt_utils import TokenManager
from authentication.verification.tasks import send_verification_email_task, send_password_reset_email_task


User = get_user_model()
logger = logging.getLogger(__name__)


class EmailVerificationService:
    """Service class to handle email verification operations"""

    @staticmethod
    def get_verification_cache_key(user_id):
        """Generate standardized cache key for user verification status"""
        return f"user_verified_status_{user_id}"

    @staticmethod
    def check_verification_status(user):
        """Check email verification status"""
        try:
            cache_key = EmailVerificationService.get_verification_cache_key(user.pk)
            cached_status = cache.get(cache_key)

            if cached_status is not None:
                logger.info(f"Using cached verification status for user {user.pk}: {cached_status}")
                return True, {
                    "success": True,
                    "data": {"is_verified": cached_status}
                }, 200

            # Query fresh from DB
            try:
                fresh_user = User.objects.get(pk=user.pk)
                is_verified = fresh_user.is_verified

                cache.set(cache_key, is_verified, timeout=3600)
                logger.info(f"Fetched verification status from DB for user {user.pk}: {is_verified}")

                return True, {
                    "success": True,
                    "data": {"is_verified": is_verified}
                }, 200

            except User.DoesNotExist:
                logger.error(f"User {user.pk} not found in database")
                return False, {
                    "success": False,
                    "error": "User not found"
                }, 404

        except Exception as e:
            logger.error(f"Error checking verification status: {e}\n{traceback.format_exc()}")
            return True, {
                "success": True,
                "data": {"is_verified": user.is_verified},
                "message": "Could not check latest status, using existing information"
            }, 200

    @staticmethod
    def verify_email(uidb64, token):
        """Verify email using verification token"""
        is_valid, user, error = TokenVerifier.verify_token(uidb64, token)

        if not is_valid:
            logger.warning(f"Invalid token verification attempt with uidb64: {uidb64}")
            return False, {
                "success": False,
                "error": error or "Invalid verification link. Please request a new one."
            }, 400

        try:
            with transaction.atomic():
                if not user.is_verified:
                    user.is_verified = True
                    user.save(update_fields=["is_verified"])
                    logger.info(f"Email verified for user {user.uuid} ({user.email})")
                else:
                    logger.info(f"Email verification attempt for already verified user: {user.uuid} ({user.email})")

            cache_key = EmailVerificationService.get_verification_cache_key(user.uuid)
            cache.set(cache_key, True, timeout=3600)
            logger.info(f"Updated verification cache for user {user.uuid} to True")

            # Include user data in response for referral bonus processing
            from authentication.serializers import UserBaseSerializer
            user_serializer = UserBaseSerializer(user)
            
            return True, {
                "success": True,
                "message": "Email verification successful.",
                "data": {
                    "user": user_serializer.data
                }
            }, 200

        except Exception as e:
            logger.error(f"Error during verification: {e}\n{traceback.format_exc()}")
            return False, {
                "success": False,
                "error": "An error occurred during verification. Please try again."
            }, 500

    @staticmethod
    def send_verification_email(user):
        """Send verification email asynchronously using Celery"""
        try:
            if user.is_verified:
                return True, {
                    "success": True,
                    "message": "Email is already verified."
                }, 200

            rate_key = f"verification_email_{user.uuid}"
            if cache.get(rate_key):
                return False, {
                    "success": False,
                    "error": "Please wait before requesting another verification email."
                }, 429

            # ✅ FIXED: Pass user.uuid as string for JSON serialization, not user object
            send_verification_email_task.delay(str(user.uuid))

            cache.set(rate_key, True, timeout=300)
            logger.info(f"Verification email task queued for {user.email}")
            return True, {
                "success": True,
                "message": "A verification link has been sent to your email."
            }, 200

        except Exception as e:
            logger.error(f"Error queueing verification email: {e}\n{traceback.format_exc()}")
            return False, {
                "success": False,
                "error": "Failed to send verification email. Please try again later."
            }, 500


class PasswordResetService:
    """Service class to handle password reset operations"""

    @staticmethod
    def request_reset(email):
        """Request password reset for given email"""
        try:
            if not email:
                return False, {
                    "success": False,
                    "error": "Email is required."
                }, 400

            rate_key = f"password_reset_{email}"
            if cache.get(rate_key):
                return True, {
                    "success": True,
                    "message": "If an account exists with this email, a password reset link will be sent."
                }, 200

            try:
                user = User.objects.get(email=email)
                send_password_reset_email_task.delay(str(user.uuid))
                logger.info(f"Password reset email task queued for {user.email}")
            except User.DoesNotExist:
                # Security best practice: don't reveal existence of email
                logger.info(f"Password reset requested for non-existent email: {email}")

            cache.set(rate_key, True, timeout=300)
            return True, {
                "success": True,
                "message": "If an account exists with this email, a password reset link will be sent."
            }, 200

        except Exception as e:
            logger.error(f"Password reset request error: {e}\n{traceback.format_exc()}")
            return True, {
                "success": True,
                "message": "If an account exists with this email, a password reset link will be sent."
            }, 200

    @staticmethod
    def confirm_reset(uidb64, token, new_password):
        """Confirm password reset using valid token and new password"""
        is_valid, user, error = TokenVerifier.verify_token(uidb64, token)
        if not is_valid:
            return False, {
                "success": False,
                "error": error or "Invalid password reset link. Please request a new one."
            }, 400

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return False, {
                "success": False,
                "error": ", ".join(e.messages)
            }, 400

        user.set_password(new_password)
        user.save(update_fields=["password"])
        TokenManager.blacklist_all_user_tokens(user.uuid)

        logger.info(f"Password reset completed for user {user.uuid}")
        return True, {
            "success": True,
            "message": "Password has been reset successfully. You can now log in with your new password."
        }, 200
