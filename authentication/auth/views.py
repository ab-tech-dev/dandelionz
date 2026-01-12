import logging
import traceback
from django.utils import timezone
from django.conf import settings
from django.middleware.csrf import get_token
from datetime import timedelta

from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.core.base_view import BaseAPIView
from authentication.core.response import standardized_response
from .services import AuthenticationService
from drf_yasg.utils import swagger_auto_schema
from authentication.serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    AuthResponseSerializer,
    TokenRefreshSerializer,
)

logger = logging.getLogger(__name__)


class UserRegistrationView(BaseAPIView):
    """
    User registration endpoint for creating new accounts.
    
    Supports registration for both CUSTOMER and VENDOR roles.
    Handles email verification token generation and optional referral code.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        operation_id="user_register",
        operation_summary="Register New User Account",
        operation_description="""Create a new user account with email, password, and optional profile information.
        
Supported roles: CUSTOMER, VENDOR

Returns JWT tokens (access and refresh) for immediate authentication.
Optionally accepts referral_code for affiliate tracking.
Email verification may be required before full account access.""",
        tags=["Authentication"],
        request_body=UserRegistrationSerializer,
        responses={
            201: AuthResponseSerializer(),
            400: AuthResponseSerializer(),
        },
        security=[],
    )
    def post(self, request):
        try:
            email = request.data.get('email')
            password = request.data.get('password')
            phone_number = request.data.get('phone_number')
            full_name = request.data.get('full_name')
            role = request.data.get('role', 'CUSTOMER').upper()
            referral_code = request.data.get('referral_code')

            if role not in ['CUSTOMER', 'VENDOR']:
                return Response(
                    standardized_response(success=False, error="Invalid user role."),
                    status=status.HTTP_400_BAD_REQUEST
                )

            success, response_data, status_code = AuthenticationService.register(
                email=email,
                password=password,
                phone_number=phone_number,
                full_name=full_name,
                role=role,
                referral_code=referral_code,
                request_meta=request.META,
                request=request
            )

            response = Response(standardized_response(**response_data), status=status_code)

            if success and status_code in (200, 201) and settings.JWT_COOKIE_SECURE:
                tokens = response_data.get('data', {}).get('tokens', {})
                refresh_token = tokens.get('refresh_token')
                refresh_expires_in = tokens.get('refresh_expires_in')

                if refresh_token and refresh_expires_in:
                    try:
                        refresh_expires_in = float(refresh_expires_in)
                        expires = timezone.now() + timedelta(seconds=refresh_expires_in)
                        response.set_cookie(
                            key=settings.JWT_COOKIE_NAME,
                            value=refresh_token,
                            expires=expires,
                            secure=True,
                            httponly=True,
                            samesite='Strict',
                            path='/',
                            domain=settings.SESSION_COOKIE_DOMAIN
                        )
                    except Exception as e:
                        logger.warning(f"Failed to set JWT cookie: {e}")

            if success:
                get_token(request)

            return response

        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="Registration failed. Please try again."),
                status=status.HTTP_400_BAD_REQUEST
            )


class UserLoginView(BaseAPIView):
    """
    User login endpoint for authentication.
    
    Authenticates users by email and password.
    Returns JWT tokens for use in subsequent API requests.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        operation_id="user_login",
        operation_summary="User Login",
        operation_description="""Authenticate a user with email and password.

Returns access and refresh JWT tokens for subsequent API requests.
Access token is used in Authorization header: Bearer {access_token}
Refresh token can be used to obtain new access tokens when expired.

For unverified email accounts, full functionality may be limited until email verification is completed.""",
        tags=["Authentication"],
        request_body=UserLoginSerializer,
        responses={
            200: AuthResponseSerializer(),
            400: AuthResponseSerializer(),
            401: AuthResponseSerializer(),
        },
        security=[],
    )
    def post(self, request):
        try:
            email = request.data.get('email')
            password = request.data.get('password')

            success, response_data, status_code = AuthenticationService.login(
                email=email,
                password=password,
                request_meta=request.META,
                request=request
            )

            response = Response(standardized_response(**response_data), status=status_code)

            if success and status_code in (200, 201) and settings.JWT_COOKIE_SECURE:
                tokens = response_data.get('data', {}).get('tokens', {})
                refresh_token = tokens.get('refresh_token')
                refresh_expires_in = tokens.get('refresh_expires_in')

                if refresh_token and refresh_expires_in:
                    try:
                        refresh_expires_in = float(refresh_expires_in)
                        expires = timezone.now() + timedelta(seconds=refresh_expires_in)
                        response.set_cookie(
                            key=settings.JWT_COOKIE_NAME,
                            value=refresh_token,
                            expires=expires,
                            secure=True,
                            httponly=True,
                            samesite='Strict',
                            path='/',
                            domain=settings.SESSION_COOKIE_DOMAIN
                        )
                    except Exception as e:
                        logger.warning(f"Failed to set JWT cookie: {e}")

            if success:
                get_token(request)

            return response

        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="An unexpected error occurred. Please try again."),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TokenRefreshView(BaseAPIView):
    """
    Token refresh endpoint for obtaining new access tokens.
    
    Uses refresh token to issue a new access token without requiring login credentials.
    Useful when access token has expired but refresh token is still valid.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        operation_id="token_refresh",
        operation_summary="Refresh Access Token",
        operation_description="""Obtain a new access token using a valid refresh token.

The refresh token can be provided in the request body or will be retrieved from cookies if JWT_COOKIE_SECURE is enabled.

Use this endpoint when your access token expires but you still have a valid refresh token.
A new access token will be returned for use in subsequent API requests.""",
        tags=["Authentication"],
        request_body=TokenRefreshSerializer,
        responses={
            200: AuthResponseSerializer(),
            400: AuthResponseSerializer(),
            401: AuthResponseSerializer(),
        },
        security=[],
    )
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if not refresh_token and settings.JWT_COOKIE_SECURE:
                refresh_token = request.COOKIES.get(settings.JWT_COOKIE_NAME)

            success, response_data, status_code = AuthenticationService.refresh_token(refresh_token)
            response = Response(standardized_response(**response_data), status=status_code)

            if success and status_code in (200, 201) and settings.JWT_COOKIE_SECURE:
                tokens = response_data.get('data', {}).get('tokens', {})
                new_refresh = tokens.get('refresh_token')
                refresh_expires_in = tokens.get('refresh_expires_in')

                if new_refresh and refresh_expires_in:
                    try:
                        refresh_expires_in = float(refresh_expires_in)
                        expires = timezone.now() + timedelta(seconds=refresh_expires_in)
                        response.set_cookie(
                            key=settings.JWT_COOKIE_NAME,
                            value=new_refresh,
                            expires=expires,
                            secure=True,
                            httponly=True,
                            samesite='Strict',
                            path='/',
                            domain=settings.SESSION_COOKIE_DOMAIN
                        )
                    except Exception as e:
                        logger.warning(f"Failed to refresh JWT cookie: {e}")

            if success:
                get_token(request)

            return response

        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="An error occurred during token refresh. Please try again."),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ValidateTokenView(BaseAPIView):
    """
    Token validation endpoint for verifying access token validity.
    
    Checks if the provided access token is valid and returns user information.
    Useful for front-end to validate if current token is still active.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="token_validate",
        operation_summary="Validate Access Token",
        operation_description="""Verify the validity of an access token and retrieve user information.

Requires a valid Bearer token in the Authorization header.
Returns user details if the token is valid and not expired.

Use this endpoint to verify token status on application startup or periodically.""",
        tags=["Authentication"],
        responses={
            200: AuthResponseSerializer(),
            400: AuthResponseSerializer(),
            401: AuthResponseSerializer(),
        },
        security=[{"Bearer": []}],
    )
    def get(self, request):
        user = request.user
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            success, response_data, status_code = AuthenticationService.validate_token(token, user)
            return Response(standardized_response(**response_data), status=status_code)

        return Response(
            standardized_response(success=False, error="No token provided"),
            status=status.HTTP_400_BAD_REQUEST
        )


class LogoutView(BaseAPIView):
    """
    User logout endpoint for session termination.
    
    Invalidates the provided refresh token and clears session cookies.
    Requires authenticated user with valid access token.
    If no refresh token is provided, all user tokens will be blacklisted for security.
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_id="user_logout",
        operation_summary="Logout User",
        operation_description="""Terminate the user session and invalidate tokens.

Requires authentication with a valid access token.
The refresh token can be provided in request body or will be read from cookies if JWT_COOKIE_SECURE is enabled.
If no refresh token is provided, all active user tokens will be invalidated for security.

JWT cookies will be cleared from the response if cookie-based authentication is enabled.""",
        tags=["Authentication"],
        request_body=TokenRefreshSerializer,
        responses={
            200: AuthResponseSerializer(),
            500: AuthResponseSerializer(),
        },
        security=[{"Bearer": []}],
    )
    def post(self, request):
        try:
            user = request.user
            refresh_token = request.data.get('refresh_token')

            if not refresh_token and settings.JWT_COOKIE_SECURE:
                refresh_token = request.COOKIES.get(settings.JWT_COOKIE_NAME)

            success, response_data, status_code = AuthenticationService.logout(user, refresh_token)
            response = Response(standardized_response(**response_data), status=status_code)

            if settings.JWT_COOKIE_SECURE:
                response.delete_cookie(
                    key=settings.JWT_COOKIE_NAME,
                    path='/',
                    domain=settings.SESSION_COOKIE_DOMAIN
                )

            return response

        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            logger.error(traceback.format_exc())
            # Return success even on error to ensure cookies are cleared
            response = Response(
                standardized_response(success=True, message="Logout completed"),
                status=status.HTTP_200_OK
            )

            if settings.JWT_COOKIE_SECURE:
                response.delete_cookie(
                    key=settings.JWT_COOKIE_NAME,
                    path='/',
                    domain=settings.SESSION_COOKIE_DOMAIN
                )

            return response


class ReferralListView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        referrals = request.user.referrals_made.all()
        data = [
            {
                "referred_user": r.referred_user.email,
                "bonus_awarded": r.bonus_awarded,
                "bonus_amount": r.bonus_amount,
                "created_at": r.created_at
            } for r in referrals
        ]
        return Response(standardized_response(success=True, data=data), status=status.HTTP_200_OK)
