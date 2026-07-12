from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.utils.translation import gettext_lazy as _

class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWTAuthentication that extends simplejwt to also check for suspended users,
    since the base implementation only checks is_active.
    """
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        
        if user.status == user.UserStatus.SUSPENDED:
            raise AuthenticationFailed(
                _("User is suspended"), code="user_suspended"
            )
            
        return user
