"""Authentication views module.

This module provides authentication-related API views including:
- User login and registration
- Token refresh and validation
- Email verification
- Password reset

Note: Main authentication views are in auth/ and verification/ submodules.
For direct imports, use:
    from authentication.auth.views import UserLoginView, UserRegistrationView, ...
    from authentication.verification.views import VerifyEmailView, SendVerificationEmailView, ...
"""

from django.shortcuts import render

# Main views are implemented in:
# - authentication.auth.views: UserLoginView, UserRegistrationView, TokenRefreshView, etc.
# - authentication.verification.views: VerifyEmailView, SendVerificationEmailView, PasswordResetView, etc.
