import logging
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

class TokenVerifier:
    """Helper class for verification token operations"""
    @staticmethod
    def verify_token(uidb64, token):
        """verify token validity and get associated user"""

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk = uid)

            # Check if token is valid
            if default_token_generator.check_token(user, token):
                logger.info(f"Token verification successful for user: {user.email}")
                return True, user, None
            
            else:
                logger.warning(f"Invalid token for user: {user.email} - Token may be expired or tampered with")
                return False, None, "Invalid or expired verification token"
            
        except User.DoesNotExist as e:
            logger.error(f"Token verification error: User not found for uid {uidb64}")
            return False, None, "Invalid verification link - user not found"
        except (TypeError, ValueError, OverflowError) as e:
            logger.error(f"Token verification error - Invalid uid format: {str(e)}")
            return False, None, "Invalid verification link format"
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return False, None, "Invalid verification link"