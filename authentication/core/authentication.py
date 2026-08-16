from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError
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


class OptionalJWTAuthentication(CustomJWTAuthentication):
    """
    Same checks as CustomJWTAuthentication, but for views that are meant to
    stay reachable by anonymous visitors no matter what's in the
    Authorization header.

    JWTAuthentication.authenticate() raises -- it doesn't return None -- on a
    missing, expired, malformed, or blacklisted token, and
    BaseAPIView.handle_exception turns that into a hard 401. DRF resolves
    authentication before permissions, so that 401 happens even on a view
    declaring permission_classes = [AllowAny]: a stale token left over from a
    just-completed logout, or one that expired while the app sat in the
    background, blocks a page that's supposed to work for a logged-out user.

    This swallows any authentication failure raised while resolving the
    token -- including a valid token belonging to a suspended user. For a
    view that's fully public, that's fine: suspension revokes account
    actions, not the ability to browse the same public catalog anyone else
    can see anonymously. Don't reuse this class on a view where a suspended
    user must be actively blocked (rather than merely treated as a visitor)
    -- keep CustomJWTAuthentication there instead.
    """
    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except (AuthenticationFailed, TokenError):
            return None