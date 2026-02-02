from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import APIException

class AccountLockedException(APIException):
    status_code = 403
    default_detail = _('Account is temporarily locked due to multiple failed attempts.')
    default_code = 'account_locked'

class EmailNotVerifiedException(APIException):
    status_code = 403
    default_detail = _('Email verification required')
    default_code = 'email_not_verified'

class InvalidTokenException(APIException):
    status_code = 401
    default_detail = _('Invalid or expired token')
    default_code = 'invalid_token'

class RateLimitedException(APIException):
    status_code = 429
    default_detail = _('Rate limit exceeded. Please try again later.')
    default_code = 'rate_limited'

class PurchaseRequiredException(APIException):
    status_code = 403
    default_detail = _('You must purchase this product to review it.')
    default_code = 'purchase_required'

class VendorNotSetupException(APIException):
    """
    Exception raised when vendor account is missing required setup.
    Status code: 400 Bad Request
    """
    status_code = 400
    default_detail = _('Vendor account is not properly configured.')
    default_code = 'vendor_not_setup'

class MissingAddressException(VendorNotSetupException):
    """
    Exception raised when vendor is missing store address/coordinates.
    This prevents product creation until store location is set.
    """
    status_code = 400
    default_detail = _('You must set your store address with coordinates before creating products.')
    default_code = 'MISSING_ADDRESS'