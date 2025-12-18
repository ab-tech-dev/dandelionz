from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from datetime import datetime, timedelta
from django.conf import settings
from django_redis import get_redis_connection
import jwt
import logging
import uuid
import time

logger = logging.getLogger(__name__)

class TokenManager:
    """Enhanced JWT token manager with Redis caching using UUID as user identifier"""

    @staticmethod
    def _get_redis_client():
        """Get a raw redis-py client"""
        return get_redis_connection("default")

    @staticmethod
    def generate_tokens(user):
        """Generate secure access and refresh tokens with enhanced claims and security"""
        try:
            refresh = RefreshToken.for_user(user)

            # Unique JWT ID for tracking
            jti = str(uuid.uuid4())

            # Custom claims
            refresh['jti'] = jti
            refresh['is_staff'] = user.is_staff
            refresh['email'] = user.email
            refresh['is_verified'] = user.is_verified
            refresh['type'] = 'refresh'
            refresh['user_uuid'] = str(user.uuid)

            # Access token claims
            access_token = refresh.access_token
            access_token['type'] = 'access'
            access_token['jti'] = str(uuid.uuid4())
            access_token['user_uuid'] = str(user.uuid)

            access_expiry = settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME', timedelta(minutes=15))
            refresh_expiry = settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME', timedelta(days=14))

            TokenManager._store_token_metadata(str(user.uuid), jti, refresh_expiry.total_seconds())

            return {
                'access_token': str(access_token),
                'refresh_token': str(refresh),
                'token_type': 'Bearer',
                'expires_in': int(access_expiry.total_seconds()),
                'refresh_expires_in': int(refresh_expiry.total_seconds()),
                'user_uuid': str(user.uuid),
                'issued_at': int(time.time())
            }

        except Exception as e:
            logger.error(f"Failed to generate tokens for user {user.email}: {str(e)}")
            raise

    @staticmethod
    def refresh_tokens(refresh_token):
        """Refresh tokens with validation and optional rotation"""
        from authentication.models import CustomUser

        try:
            token = RefreshToken(refresh_token)
            jti = token.get('jti')

            if not jti or TokenManager.is_token_blacklisted(jti):
                logger.warning(f"Attempt to use blacklisted token with JTI: {jti}")
                raise TokenError("Token is blacklisted")

            user_uuid = token.get('user_uuid')
            if not user_uuid:
                raise TokenError("Invalid token payload: missing user_uuid")

            try:
                user = CustomUser.objects.get(uuid=user_uuid)
            except CustomUser.DoesNotExist:
                logger.warning(f"Token refresh attempted for non-existent user UUID: {user_uuid}")
                raise TokenError("Invalid token")

            if not user.is_active:
                logger.warning(f"Token refresh attempted for inactive user: {user.email}")
                TokenManager.blacklist_token(jti)
                raise TokenError("User is inactive")

            if settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKEN', True):
                TokenManager.blacklist_token(jti)

            return TokenManager.generate_tokens(user)

        except TokenError as e:
            logger.warning(f"Token refresh error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {str(e)}")
            raise TokenError(f"Token refresh failed: {str(e)}")

    @staticmethod
    def validate_token(token_string):
        """Validate token without database lookup"""
        try:
            unverified = jwt.decode(token_string, options={"verify_signature": False})
            alg = unverified.get('alg', settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'))

            decoded = jwt.decode(
                token_string,
                settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
                algorithms=[alg],
                options={"verify_signature": True}
            )

            token_type = decoded.get('token_type', decoded.get('type', 'access'))
            jti = decoded.get('jti')
            user_uuid = decoded.get('user_uuid')

            if jti and TokenManager.is_token_blacklisted(jti):
                logger.warning(f"Attempt to use blacklisted token with JTI: {jti}")
                return False, None, None

            exp = decoded.get('exp', 0)
            if exp < time.time():
                logger.debug(f"Token expired at {datetime.fromtimestamp(exp).isoformat()}")
                return False, None, None

            return True, user_uuid, token_type

        except jwt.PyJWTError as e:
            logger.debug(f"Token validation error: {str(e)}")
            return False, None, None

    @staticmethod
    def blacklist_token(jti):
        """Blacklist a token by JTI"""
        if not jti:
            return False
        try:
            redis_client = TokenManager._get_redis_client()
            blacklist_key = f"blacklisted_token:{jti}"
            timeout = settings.SIMPLE_JWT.get('BLACKLIST_TIMEOUT', 86400)
            redis_client.setex(blacklist_key, timeout, "1")
            return True
        except Exception as e:
            logger.error(f"Error blacklisting token in Redis: {str(e)}")
            return False

    @staticmethod
    def is_token_blacklisted(jti):
        """Check if token is blacklisted"""
        if not jti:
            return False
        try:
            redis_client = TokenManager._get_redis_client()
            blacklist_key = f"blacklisted_token:{jti}"
            return redis_client.exists(blacklist_key) > 0
        except Exception as e:
            logger.error(f"Error checking token blacklist in Redis: {str(e)}")
            return False

    @staticmethod
    def _store_token_metadata(user_uuid, jti, expiry_seconds):
        """Store token metadata in Redis for blacklisting"""
        try:
            redis_client = TokenManager._get_redis_client()
            user_tokens_key = f"user_tokens:{user_uuid}"
            pipe = redis_client.pipeline()
            pipe.sadd(user_tokens_key, jti)
            pipe.expire(user_tokens_key, int(expiry_seconds))
            pipe.execute()
        except Exception as e:
            logger.error(f"Error storing token metadata in Redis: {str(e)}")

    @staticmethod
    def blacklist_all_user_tokens(user_uuid):
        """Blacklist all tokens for a specific user"""
        try:
            redis_client = TokenManager._get_redis_client()
            user_tokens_key = f"user_tokens:{user_uuid}"
            active_tokens = redis_client.smembers(user_tokens_key)
            if not active_tokens:
                return 0
            pipe = redis_client.pipeline()
            blacklist_timeout = settings.SIMPLE_JWT.get('BLACKLIST_TIMEOUT', 86400)
            for jti in active_tokens:
                jti_str = jti.decode('utf-8') if isinstance(jti, bytes) else jti
                pipe.setex(f"blacklisted_token:{jti_str}", blacklist_timeout, 1)
            pipe.delete(user_tokens_key)
            pipe.execute()
            logger.info(f"Blacklisted {len(active_tokens)} tokens for user {user_uuid}")
            return len(active_tokens)
        except Exception as e:
            logger.error(f"Error blacklisting user tokens in Redis: {str(e)}")
            return 0

    @staticmethod
    def get_user_active_tokens_count(user_uuid):
        """Get count of active tokens for a user"""
        try:
            redis_client = TokenManager._get_redis_client()
            return redis_client.scard(f"user_tokens:{user_uuid}")
        except Exception as e:
            logger.error(f"Error getting user token count from Redis: {str(e)}")
            return 0

    @staticmethod
    def cleanup_expired_tokens():
        """Utility method to clean up expired token metadata"""
        try:
            # Currently a placeholder; Redis handles expiry automatically
            logger.info("Token cleanup completed")
            return True
        except Exception as e:
            logger.error(f"Error during token cleanup: {str(e)}")
            return False
