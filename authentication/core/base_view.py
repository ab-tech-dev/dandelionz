import logging
import traceback
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    ValidationError,
)
from rest_framework_simplejwt.exceptions import TokenError

from .response import standardized_response

logger = logging.getLogger(__name__)

class BaseAPIView(APIView):
    """Base class for all API views with common error handling and response formatting"""

    def _extract_error_message(self, detail):
        """
        Keep structured error payloads (dict/list) for serializer errors and
        normalize simple details to strings.
        """
        if isinstance(detail, (dict, list)):
            return detail
        return str(detail)

    def handle_exception(self, exc):
        """Standardized exception handling for all API views"""
        request = getattr(self, "request", None)
        method = getattr(request, "method", "UNKNOWN")
        path = getattr(request, "path", "UNKNOWN")
        user = getattr(request, "user", None)
        user_id = getattr(user, "uuid", None) or getattr(user, "id", None) or "anonymous"

        if isinstance(exc, AuthenticationFailed):
                return Response(standardized_response(
                    success=False,
                    error = str(exc)
                ),
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        elif isinstance(exc, TokenError):
             return Response(
                  standardized_response(
                       success=False,
                       error = 'Invalid or expired token'
                  ),
                  status=status.HTTP_401_UNAUTHORIZED
             )
        
        if isinstance(exc, MethodNotAllowed):
            return Response(
                standardized_response(
                    success=False,
                    error=str(exc)
                ),
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        if isinstance(exc, ValidationError):
            logger.warning(
                "Validation error on %s %s (user=%s): %s",
                method,
                path,
                user_id,
                exc.detail,
            )
            return Response(
                standardized_response(
                    success=False,
                    error=self._extract_error_message(exc.detail)
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        if isinstance(exc, APIException):
            error_code = None
            if hasattr(exc, "get_codes"):
                try:
                    error_code = exc.get_codes()
                except Exception:
                    error_code = None

            logger.warning(
                "API exception on %s %s (user=%s, status=%s, code=%s): %s",
                method,
                path,
                user_id,
                getattr(exc, "status_code", "unknown"),
                error_code,
                exc.detail,
            )
            return Response(
                standardized_response(
                    success=False,
                    error=self._extract_error_message(exc.detail),
                    error_code=error_code,
                ),
                status=exc.status_code
            )

        logger.error("Unexpected error on %s %s (user=%s): %s", method, path, user_id, str(exc))
        logger.error(traceback.format_exc())

        return Response(
             standardized_response(
                  success=False,
                  error = "An unexpected error occured"
             ),
             status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
