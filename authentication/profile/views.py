import logging
import traceback
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from authentication.core.base_view import BaseAPIView
from authentication.core.response import standardized_response
from .services import ProfileService
from authentication.serializers import UserProfileSerializer, UserProfileUpdateSerializer

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

logger = logging.getLogger(__name__)

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class UserProfileView(BaseAPIView):
    """
    API endpoint for user profile operations.
    Provides GET (view), PUT (update full), and PATCH (partial update) methods.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    # ---------------------------
    # GET (View Profile)
    # ---------------------------
    @swagger_auto_schema(
        operation_summary="Retrieve the authenticated user's profile",
        operation_description=(
            "Returns the authenticated user's profile. "
            "You must provide an Authorization header in Swagger using:\n\n"
            "`Authorization: Bearer <your_token>`"
        ),
        manual_parameters=[
            openapi.Parameter(
                'verbose',
                openapi.IN_QUERY,
                description="Include extra details if True (e.g. connected accounts, vendor info, etc.)",
                type=openapi.TYPE_BOOLEAN
            ),
            openapi.Parameter(   # 👇 this makes Swagger show the token input
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer access token (e.g. 'Bearer eyJ0eXAiOiJKV1QiLCJh...')",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        responses={
            200: openapi.Response("Profile data retrieved successfully", UserProfileSerializer),
            401: "Unauthorized — missing or invalid token",
            500: "Server error while retrieving profile"
        }
    )
    def get(self, request):
        """Get user profile data"""
        try:
            logger.info(f"Profile request for user {request.user.email} ({request.user.role})")
            user_data = ProfileService.get_profile(request.user, request=request)
            return Response(
                standardized_response(success=True, data=user_data),
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Profile fetch error for {request.user.email}: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, message="Failed to retrieve profile"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ---------------------------
    # PUT (Full Update)
    # ---------------------------
    @swagger_auto_schema(
        operation_summary="Update full user profile",
        operation_description=(
            "Updates all editable fields in the user's profile. "
            "Requires Bearer token in the Authorization header."
        ),
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer access token (e.g. 'Bearer eyJ0eXAiOiJKV1QiLCJh...')",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=UserProfileUpdateSerializer,
        responses={
            200: openapi.Response("Profile updated successfully", UserProfileSerializer),
            400: "Invalid input data",
            401: "Unauthorized",
            500: "Profile update failed"
        }
    )
    def put(self, request):
        """Update full user profile"""
        try:
            success, response_data, status_code = ProfileService.update_profile(
                user=request.user,
                data=request.data,
                files=request.FILES,
                request=request
            )
            return Response(
                standardized_response(**response_data),
                status=status_code
            )
        except Exception as e:
            logger.error(f"Profile update error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="Profile update failed"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ---------------------------
    # PATCH (Partial Update)
    # ---------------------------
    @swagger_auto_schema(
        operation_summary="Partially update user profile",
        operation_description=(
            "Allows updating one or more fields of the profile without affecting others. "
            "Requires Bearer token authentication."
        ),
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description="Bearer access token (e.g. 'Bearer eyJ0eXAiOiJKV1QiLCJh...')",
                type=openapi.TYPE_STRING,
                required=True
            ),
        ],
        request_body=UserProfileUpdateSerializer,
        responses={
            200: openapi.Response("Profile updated successfully", UserProfileSerializer),
            400: "Invalid input data",
            401: "Unauthorized",
            500: "Profile patch failed"
        }
    )
    def patch(self, request):
        """Partial user profile update"""
        try:
            success, response_data, status_code = ProfileService.update_profile(
                user=request.user,
                data=request.data,
                files=request.FILES,
                request=request
            )
            return Response(
                standardized_response(**response_data),
                status=status_code
            )
        except Exception as e:
            logger.error(f"Profile patch error: {str(e)}")
            logger.error(traceback.format_exc())
            return Response(
                standardized_response(success=False, error="Profile update failed"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
