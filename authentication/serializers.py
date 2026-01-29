from rest_framework import serializers
from .models import CustomUser
import re

# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# ------------------------------------------------------
# BASE USER SERIALIZER
# ------------------------------------------------------
from rest_framework import serializers

class UserBaseSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'uuid',
            'email',
            'full_name',
            'phone_number',
            'profile_picture',
            'role',
            'is_verified',
            'created_at',
            'referral_code'
        ]
        read_only_fields = ['uuid', 'email', 'role', 'created_at', 'is_verified', 'referral_code']
        ref_name = "AuthenticationUserBase"

    def get_profile_picture(self, obj):
        try:
            if hasattr(obj, 'profile_picture') and obj.profile_picture:
                # Prepend your Cloudinary base URL
                return f"https://res.cloudinary.com/dhpny4uce/{obj.profile_picture}"
        except Exception:
            pass
        return None





# ------------------------------------------------------
# TOKEN SERIALIZERS
# ------------------------------------------------------
class TokenSerializer(serializers.Serializer):
    access_token = serializers.CharField(help_text="JWT access token for API requests")
    refresh_token = serializers.CharField(help_text="JWT refresh token for obtaining new access tokens")
    refresh_expires_in = serializers.FloatField(help_text="Refresh token expiration time in seconds")


class AuthDataSerializer(serializers.Serializer):
    user = UserBaseSerializer(help_text="User profile information")
    tokens = TokenSerializer(help_text="JWT tokens for authentication")
    is_new_user = serializers.BooleanField(required=False, help_text="Indicates if this is a newly created account")
    email_verified = serializers.BooleanField(required=False, help_text="Email verification status")


# ------------------------------------------------------
# AUTH SERIALIZERS
# ------------------------------------------------------
class UserRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="User email address")
    password = serializers.CharField(write_only=True, min_length=8, help_text="User password (minimum 8 characters)")
    phone_number = serializers.CharField(required=False, allow_blank=True, help_text="User phone number")
    full_name = serializers.CharField(required=False, allow_blank=True, help_text="User full name")
    role = serializers.ChoiceField(
        choices=CustomUser.Role.choices,
        required=True,
        help_text="User role: CUSTOMER or VENDOR"
    )
    referral_code = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Referral code from an existing user for affiliate tracking"
    )

    def validate_email(self, value):
        """Validate email format and ensure it's a complete email address"""
        if not value or not isinstance(value, str):
            raise serializers.ValidationError("Email must be a non-empty string")
        
        value = value.strip()
        
        # Check basic format
        if not EMAIL_REGEX.match(value):
            raise serializers.ValidationError(
                "Invalid email format. Email must contain both local part (username) and domain (e.g., user@example.com)"
            )
        
        # Ensure it has both local and domain parts
        if '@' not in value:
            raise serializers.ValidationError("Email must contain @ symbol")
        
        local_part, domain = value.rsplit('@', 1)
        
        # Local part should not be empty
        if not local_part:
            raise serializers.ValidationError("Email local part (before @) cannot be empty")
        
        # Domain should have at least one dot
        if '.' not in domain:
            raise serializers.ValidationError("Email domain must contain a dot (e.g., example.com)")
        
        # Domain parts should not be empty
        parts = domain.split('.')
        if any(not part for part in parts):
            raise serializers.ValidationError("Email domain parts cannot be empty")
        
        return value


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="User email address")
    password = serializers.CharField(write_only=True, help_text="User password")


class TokenRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(help_text="JWT refresh token")


class AuthResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether the operation was successful")
    message = serializers.CharField(required=False, help_text="Human-readable message")
    data = AuthDataSerializer(required=False, help_text="Response data containing user and tokens")
    error = serializers.CharField(required=False, help_text="Error message if operation failed")


# ------------------------------------------------------
# EMAIL VERIFICATION SERIALIZERS
# ------------------------------------------------------
class VerifyEmailRequestSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True, help_text="Base64 encoded user ID")
    token = serializers.CharField(required=True, help_text="Email verification token")


class VerifyEmailResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether verification was successful")
    message = serializers.CharField(help_text="Result message")
    data = serializers.DictField(required=False, allow_null=True, help_text="User data if successful")


class SendVerificationEmailResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether email was sent successfully")
    message = serializers.CharField(help_text="Result message")


class VerificationStatusResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether the request was successful")
    data = serializers.DictField(help_text="Contains 'is_verified': true/false")
    message = serializers.CharField(help_text="Status message")


# ------------------------------------------------------
# PASSWORD RESET SERIALIZERS
# ------------------------------------------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="User email address to reset password for")


class PasswordResetResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether the request was processed")
    message = serializers.CharField(help_text="Result message")


class ConfirmPasswordResetRequestSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True, help_text="Base64 encoded user ID")
    token = serializers.CharField(required=True, help_text="Password reset token from email")
    new_password = serializers.CharField(
        required=True,
        min_length=8,
        write_only=True,
        help_text="New password for the account (minimum 8 characters)"
    )


class ConfirmPasswordResetResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether password reset was successful")
    message = serializers.CharField(help_text="Result message")


# ------------------------------------------------------
# REFERRAL SERIALIZERS
# ------------------------------------------------------
class ReferralResponseSerializer(serializers.Serializer):
    referred_user = serializers.CharField(help_text="Email of the referred user")
    bonus_awarded = serializers.BooleanField(help_text="Whether the referral bonus was awarded")
    bonus_amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Referral bonus amount")
    created_at = serializers.DateTimeField(help_text="When the referral was created")


class ReferralListResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(help_text="Whether the request was successful")
    data = ReferralResponseSerializer(many=True, help_text="List of referrals made by the user")
    message = serializers.CharField(required=False, help_text="Result message")
