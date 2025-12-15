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
from drf_yasg import openapi
from authentication.serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    AuthResponseSerializer
)

logger = logging.getLogger(__name__)


class UserRegistrationView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        request_body=UserRegistrationSerializer,
        responses={201: AuthResponseSerializer, 400: AuthResponseSerializer}
    )
    def post(self, request):
        try:
            email = request.data.get('email')
            password = request.data.get('password')
            phone_number = request.data.get('phone_number')
            full_name = request.data.get('full_name')
            role = request.data.get('role', 'CUSTOMER').upper()

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
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        request_body=UserLoginSerializer,
        responses={200: AuthResponseSerializer, 400: AuthResponseSerializer}
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
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'refresh_token': openapi.Schema(type=openapi.TYPE_STRING)}
        ),
        responses={200: AuthResponseSerializer, 400: AuthResponseSerializer}
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
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        responses={200: AuthResponseSerializer, 400: AuthResponseSerializer, 401: AuthResponseSerializer}
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
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'refresh_token': openapi.Schema(type=openapi.TYPE_STRING)}
        ),
        responses={200: AuthResponseSerializer, 500: AuthResponseSerializer}
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
                    domain=settings.JWT_COOKIE_DOMAIN
                )

            return response

        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            logger.error(traceback.format_exc())
            response = Response(
                standardized_response(success=True, message="Logout not processed"),
                status=status.HTTP_200_OK
            )

            if settings.JWT_COOKIE_SECURE:
                response.delete_cookie(
                    key=settings.JWT_COOKIE_NAME,
                    path='/',
                    domain=settings.JWT_COOKIE_DOMAIN
                )

            return response
