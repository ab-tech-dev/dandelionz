from rest_framework import serializers
from .models import CustomUser, Vendor, Customer


# ------------------------------------------------------
# BASE USER SERIALIZER
# ------------------------------------------------------
class UserBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id',
            'email',
            'full_name',
            'phone_number',
            'profile_picture',
            'role',
            'is_verified',
            'created_at',
        ]
        read_only_fields = ['email', 'role', 'created_at', 'is_verified']


# ------------------------------------------------------
# VENDOR PROFILE SERIALIZER
# ------------------------------------------------------
class VendorProfileSerializer(serializers.ModelSerializer):
    user = UserBaseSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = [
            'user',
            'store_name',
            'store_description',
            'business_registration_number',
            'address',
            'bank_name',
            'account_number',
            'recipient_code',
            'is_verified_vendor',
        ]
        read_only_fields = ['user']


# ------------------------------------------------------
# CUSTOMER PROFILE SERIALIZER
# ------------------------------------------------------
class CustomerProfileSerializer(serializers.ModelSerializer):
    user = UserBaseSerializer(read_only=True)

    class Meta:
        model = Customer
        fields = [
            'user',
            'shipping_address',
            'city',
            'country',
            'postal_code',
            'loyalty_points',
        ]
        read_only_fields = ['user']


# ------------------------------------------------------
# ADMIN PROFILE SERIALIZER (basic user details)
# ------------------------------------------------------
class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id',
            'email',
            'full_name',
            'phone_number',
            'profile_picture',
            'role',
            'is_verified',
            'created_at',
        ]


# ------------------------------------------------------
# AUTH SERIALIZERS
# ------------------------------------------------------
class UserRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    phone_number = serializers.CharField(required=False)
    full_name = serializers.CharField(required=False)
    role = serializers.ChoiceField(choices=CustomUser.Role.choices, required=True)


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class TokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    refresh_expires_in = serializers.FloatField()


class AuthResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = TokenResponseSerializer(required=False)
    error = serializers.CharField(required=False)


# ------------------------------------------------------
# USER PROFILE SERIALIZERS
# ------------------------------------------------------
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id',
            'full_name',
            'email',
            'phone_number',
            'profile_picture',
            'role',
            'created_at'
        ]
        read_only_fields = ['id', 'email', 'role', 'created_at']


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['full_name', 'phone_number', 'profile_picture']


# ------------------------------------------------------
# EMAIL VERIFICATION SERIALIZERS
# ------------------------------------------------------
class VerifyEmailRequestSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True, help_text="Base64 encoded user ID")
    token = serializers.CharField(required=True, help_text="Email verification token")


class VerifyEmailResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.DictField(required=False, allow_null=True)


class SendVerificationEmailResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class VerificationStatusResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField(help_text="Contains is_verified: true/false")
    message = serializers.CharField()


# ------------------------------------------------------
# PASSWORD RESET SERIALIZERS
# ------------------------------------------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(help_text="User email address")


class PasswordResetResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class ConfirmPasswordResetRequestSerializer(serializers.Serializer):
    uid = serializers.CharField(required=True, help_text="Base64 encoded user ID")
    token = serializers.CharField(required=True, help_text="Password reset token")
    new_password = serializers.CharField(required=True, min_length=8, help_text="New password for the account")


class ConfirmPasswordResetResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
