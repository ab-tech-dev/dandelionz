import logging
import traceback
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from authentication.core.base_view import BaseAPIView
from authentication.core.response import standardized_response
from .services import EmailVerificationService, PasswordResetService

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.serializers import (
    VerifyEmailRequestSerializer,
    VerifyEmailResponseSerializer,
    SendVerificationEmailResponseSerializer,
    VerificationStatusResponseSerializer,
    PasswordResetRequestSerializer,
    PasswordResetResponseSerializer,
    ConfirmPasswordResetRequestSerializer,
    ConfirmPasswordResetResponseSerializer
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# VERIFY EMAIL
# ---------------------------------------------------------------------
class VerifyEmailView(BaseAPIView):
    """Endpoint for verifying email with token"""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        operation_summary="Verify user's email using UID and token",
        operation_description="Accepts a UID and token to verify a user's email. Works for both POST and GET methods.",
        request_body=VerifyEmailRequestSerializer,
        responses={
            200: VerifyEmailResponseSerializer,
            400: "Missing or invalid data",
            500: "Server error during verification"
        }
    )
    def post(self, request):
        try:
            uidb64 = request.data.get('uid') or request.query_params.get('uid')
            token = request.data.get('token') or request.query_params.get('token')

            if not uidb64 or not token:
                return Response(
                    standardized_response(success=False, error="Missing required fields"),
                    status=status.HTTP_400_BAD_REQUEST
                )

            success, response_data, status_code = EmailVerificationService.verify_email(uidb64=uidb64, token=token)
            return Response(standardized_response(**response_data), status=status_code)

        except Exception as e:
            logger.error(f"Email verification error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="Email verification failed. Please try again."),
                status=status.HTTP_400_BAD_REQUEST
            )

    @swagger_auto_schema(
        operation_summary="Alternative GET verification endpoint",
        operation_description="Accepts UID and token via query parameters (?uid=...&token=...).",
        manual_parameters=[
            openapi.Parameter('uid', openapi.IN_QUERY, description="User UID (Base64 encoded)", type=openapi.TYPE_STRING),
            openapi.Parameter('token', openapi.IN_QUERY, description="Verification token", type=openapi.TYPE_STRING)
        ],
        responses={200: VerifyEmailResponseSerializer}
    )
    def get(self, request):
        return self.post(request)


# ---------------------------------------------------------------------
# SEND VERIFICATION EMAIL
# ---------------------------------------------------------------------
class SendVerificationEmailView(BaseAPIView):
    """Endpoint for sending verification email"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_summary="Send email verification link",
        operation_description="Authenticated users can request a new email verification link.",
        responses={
            200: SendVerificationEmailResponseSerializer,
            400: "Failed to send email",
            401: "Unauthorized"
        }
    )
    def post(self, request):
        try:
            success, response_data, status_code = EmailVerificationService.send_verification_email(request.user)
            return Response(standardized_response(**response_data), status=status_code)
        except Exception as e:
            logger.error(f"Send verification email error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="Failed to send verification email."),
                status=status.HTTP_400_BAD_REQUEST
            )


# ---------------------------------------------------------------------
# CHECK VERIFICATION STATUS
# ---------------------------------------------------------------------
class CheckVerificationStatusView(BaseAPIView):
    """Endpoint for checking verification status"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    @swagger_auto_schema(
        operation_summary="Check email verification status",
        operation_description="Returns whether the authenticated user's email is verified.",
        responses={
            200: VerificationStatusResponseSerializer,
            401: "Unauthorized"
        }
    )
    def get(self, request):
        try:
            success, response_data, status_code = EmailVerificationService.check_verification_status(request.user)
            logger.info(f"Verification status check for user {request.user.pk}: {response_data.get('data', {}).get('is_verified')}")
            return Response(standardized_response(**response_data), status=status_code)
        except Exception as e:
            logger.error(f"Check verification status error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(
                    success=True,
                    data={'is_verified': request.user.is_verified},
                    message="Could not check latest status, using existing information."
                ), status=status.HTTP_200_OK
            )


# ---------------------------------------------------------------------
# PASSWORD RESET REQUEST
# ---------------------------------------------------------------------
class PasswordRestView(BaseAPIView):
    """Endpoint for requesting password reset"""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        operation_summary="Request password reset email",
        operation_description="Accepts an email and sends a password reset link if the account exists.",
        request_body=PasswordResetRequestSerializer,
        responses={
            200: PasswordResetResponseSerializer,
            400: "Invalid input"
        }
    )
    def post(self, request):
        try:
            email = request.data.get('email')
            if not email:
                return Response(
                    standardized_response(success=False, error="Email is required"),
                    status=status.HTTP_400_BAD_REQUEST
                )
            success, response_data, status_code = PasswordResetService.request_reset(email=email)
            return Response(standardized_response(**response_data), status=status_code)
        except Exception as e:
            logger.error(f"Password reset error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=True, message="If an account exists with this email, a reset link will be sent."),
                status=status.HTTP_200_OK
            )


# ---------------------------------------------------------------------
# CONFIRM PASSWORD RESET
# ---------------------------------------------------------------------
class ConfirmPasswordResetView(BaseAPIView):
    """Endpoint for confirming password reset with token"""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(
        operation_summary="Confirm password reset using UID, token, and new password",
        operation_description="Verifies the password reset token and sets a new password.",
        request_body=ConfirmPasswordResetRequestSerializer,
        responses={
            200: ConfirmPasswordResetResponseSerializer,
            400: "Invalid or missing fields"
        }
    )
    def post(self, request):
        try:
            uidb64 = request.data.get('uid') or request.query_params.get('uid')
            token = request.data.get('token') or request.query_params.get('token')
            new_password = request.data.get('new_password')

            if not uidb64 or not token or not new_password:
                return Response(
                    standardized_response(success=False, error="Missing required fields"),
                    status=status.HTTP_400_BAD_REQUEST
                )

            success, response_data, status_code = PasswordResetService.confirm_reset(
                uidb6=uidb64, token=token, new_password=new_password
            )
            return Response(standardized_response(**response_data), status=status_code)
        except Exception as e:
            logger.error(f"Password reset confirmation error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="Password reset failed. Please try again."),
                status=status.HTTP_400_BAD_REQUEST
            )
