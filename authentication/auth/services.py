import logging
import traceback
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from authentication.serializers import UserBaseSerializer
from authentication.core.jwt_utils import TokenManager
from authentication.core.ip_utils import get_client_ip
from authentication.models import CustomUser
from rest_framework_simplejwt.tokens import RefreshToken
from authentication.verification.tasks import send_verification_email_task

logger = logging.getLogger(__name__)


class AuthenticationService:
    """Service class to handle authentication-related business logic"""

    @staticmethod
    def register(email, password, phone_number=None, full_name=None, role='CUSTOMER',
                 referral_code=None, request_meta=None, request=None):
        """Handle user registration with email and password"""
        if not email or not password:
            return False, {
                "success": False,
                "error": "Email and password are required."
            }, 400

        if request_meta:
            ip = get_client_ip(request_meta)
            logger.info(f"Registration attempt from IP: {ip}")

        try:
            if CustomUser.objects.filter(email=email).exists():
                return False, {"success": False, "error": "A user with this email already exists"}, 400

            try:
                validate_password(password)
            except ValidationError as e:
                return False, {"success": False, "error": ", ".join(e.messages)}, 400

            user = CustomUser.objects.create_user(
                email=email,
                role=role,
                password=password,
                is_verified=False
            )

            if full_name:
                user.full_name = full_name
                user.save(update_fields=['full_name'])
            if phone_number:
                user.phone_number = phone_number
                user.save(update_fields=['phone_number'])

            # REFERRAL CODE HANDLING
            if referral_code:
                try:
                    from authentication.core.referral_service import ReferralService
                    success_ref, referral, message = ReferralService.create_referral(referral_code, user)
                    if success_ref:
                        logger.info(f"Referral created: {referral.email} referred {user.email}")
                    else:
                        logger.warning(f"Invalid referral code or error: {message}")
                except Exception as e:
                    logger.error(f"Error processing referral: {str(e)}")

            # Queue verification email
            if user.email and settings.REQUIRE_EMAIL_VERIFICATION:
                try:
                    # Convert UUID to string for Celery JSON serialization
                    send_verification_email_task.delay(str(user.uuid))
                    logger.info(f"Queued verification email for new user: {user.email}")
                except Exception as e:
                    logger.error(f"Failed to queue verification email task for user {user.pk}: {str(e)}")

            context = {}
            if request:
                context['request'] = request
            serializer = UserBaseSerializer(user, context=context)
            tokens = TokenManager.generate_tokens(user)
            logger.info(f"Registration successful for user: {user.email}")

            return True, {
                "success": True,
                "data": {
                    'user': serializer.data,
                    'tokens': tokens,
                    'is_new_user': True,
                    'email_verified': user.is_verified,
                }
            }, 201

        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return False, {"success": False, "error": "Registration failed. Please try again"}, 400

    @staticmethod
    def login(email, password, request_meta=None, request=None):
        """Handle user login with email and password"""
        if not email or not password:
            return False, {"success": False, "error": "Email and password are required."}, 400

        if request_meta:
            ip = get_client_ip(request_meta)
            logger.info(
                f"Login attempt from IP: {ip}, User-agent: {request_meta.get('HTTP_USER_AGENT')}"
            )

        try:
            if cache.get(f"account_lockout:{email}"):
                logger.warning(f"Login attempt for locked account: {email}")
                return False, {
                    "success": False,
                    "error": "Account temporarily locked due to multiple failed attempts. Try again later.",
                    "lockout": True,
                }, 403

            try:
                if not CustomUser.objects.filter(email=email).exists():
                    logger.warning(f"Login attempt for non-existent email: {email}")
                    failed_attempts = cache.get(f"failed_logins:{email}", 0) + 1
                    cache.set(f"failed_logins:{email}", failed_attempts, timeout=1800)
                    return False, {
                        "success": False,
                        "error": "Invalid email or password"
                    }, 401
            except Exception as user_check_error:
                logger.error(f"Error checking user existence: {str(user_check_error)}")
                return False, {"success": False, "error": "Database error occurred"}, 500

            user = authenticate(username=email, password=password)
            if not user:
                failed_attempts = cache.get(f"failed_logins:{email}", 0) + 1
                cache.set(f"failed_logins:{email}", failed_attempts, timeout=1800)

                if failed_attempts >= 5:
                    cache.set(f"account_lockout:{email}", True, timeout=900)
                    logger.warning(f"Account locked due to failed attempts: {email}")
                    return False, {
                        "success": False,
                        "error": "Account temporarily locked due to multiple failed attempts. Try again later."
                    }, 403

                logger.warning(f"Failed login attempt for email: {email}")
                return False, {"success": False, "error": "Invalid email or password"}, 401

            if not user.is_active:
                logger.warning(f"Login attempt for disabled account: {email}")
                return False, {"success": False, "error": "Account is disabled. Please contact support."}, 403

            cache.delete(f"failed_logins:{email}")
            context = {}
            if request:
                context['request'] = request

            try:
                serializer = UserBaseSerializer(user, context=context)
            except Exception as serializer_error:
                logger.error(f"User serialization error: {str(serializer_error)}")
                return False, {"success": False, "error": "User data serialization failed."}, 500

            try:
                tokens = TokenManager.generate_tokens(user)
            except Exception as token_error:
                logger.error(f"Token generation error: {str(token_error)}")
                return False, {"success": False, "error": "Token generation failed."}, 500

            try:
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
            except Exception as save_error:
                logger.warning(f"Failed to update last login: {str(save_error)}")

            if request_meta:
                ip = get_client_ip(request_meta)
                logger.info(f"Login successful for user: {user.email} from IP {ip}")

            return True, {
                "success": True,
                "data": {
                    'user': serializer.data,
                    'tokens': tokens,
                    'email_verified': user.is_verified,
                    'verification_needed': not user.is_verified and settings.REQUIRE_EMAIL_VERIFICATION
                }
            }, 200

        except ValidationError as ve:
            logger.error(f"Validation error during login: {str(ve)}")
            return False, {"success": False, "error": f"Validation error: {str(ve)}"}, 400

        except Exception as e:
            logger.error(f"Unexpected login error {str(e)}")
            logger.error(f"Login error traceback: {traceback.format_exc()}")
            return False, {"success": False, "error": "Authentication failed. Please try again"}, 500

    @staticmethod
    def refresh_token(refresh_token):
        """Refresh an authentication token"""
        if not refresh_token:
            return False, {"success": False, "error": "Refresh token is required"}, 400

        try:
            tokens = TokenManager.refresh_tokens(refresh_token)
            return True, {
                "success": True,
                "data": {
                    'access_token': tokens['access_token'],
                    'refresh_token': tokens['refresh_token'],
                    'token_type': tokens['token_type'],
                    'expires_in': tokens['expires_in']
                }
            }, 200
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            return False, {"success": False, "error": "An error occurred during token refresh"}, 500

    @staticmethod
    def validate_token(token, user):
        """Validate a token and check if it belongs to the user"""
        is_valid, user_uuid, token_type = TokenManager.validate_token(token)

        if not is_valid or user_uuid != user.pk:
            logger.warning(f"Token validation failed: expected user {user.pk}, got {user_uuid}")
            return False, {"success": False, "error": "Token validation failed"}, 401

        from authentication.verification.services import EmailVerificationService
        success, verification_response, _ = EmailVerificationService.check_verification_status(user)
        is_verified = user.is_verified

        if success:
            is_verified = verification_response.get('data', {}).get('is_verified', is_verified)
        else:
            logger.error(f"Error checking verification status for user {user.pk}")

        logger.info(f"Token validation retrieved verification status for user {user.pk}: is_verified = {is_verified}")

        return True, {"success": True, "data": {'valid': True, 'user_uuid': user.pk, 'email_verified': is_verified}}, 200

    @staticmethod
    def logout(user, refresh_token=None):
        """Handle user logout and invalidate token if provided"""
        blacklisted_count = 0
        
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                jti = token.get('jti')
                if jti:
                    TokenManager.blacklist_token(jti)
                    blacklisted_count += 1
                    logger.info(f"Refresh token blacklisted during logout: {jti}")
            except Exception as e:
                logger.warning(f"Error blacklisting refresh token during logout: {str(e)}")
        else:
            # If no refresh token provided, blacklist all user tokens for security
            try:
                blacklisted_count = TokenManager.blacklist_all_user_tokens(str(user.uuid))
                logger.info(f"All tokens blacklisted for user {user.pk} during logout")
            except Exception as e:
                logger.warning(f"Error blacklisting all user tokens during logout: {str(e)}")

        logger.info(f"User logged out: {user.pk} ({blacklisted_count} token(s) blacklisted)")
        return True, {
            "success": True, 
            "message": "Successfully logged out",
            "data": {
                "tokens_blacklisted": blacklisted_count
            }
        }, 200
