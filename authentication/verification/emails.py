import logging
import traceback
from django.conf import settings
from django.core.mail import send_mail

from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model


User = get_user_model()
logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending user-related emails"""

    @staticmethod
    def send_verification_email(user, max_retries=3):
        """Send verification email to user with verification link"""
        for attempt in range(max_retries):
            try:
                # Encode user ID for verification link
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)

                verify_url = f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"

                subject = f"{settings.APP_NAME} - Verify Your Email Address"

                context = {
                    'user': user,
                    'verify_url': verify_url,
                    'app_name': settings.APP_NAME,
                }

                html_message = render_to_string('emails/verify_email.html', context)
                plain_message = (
                    f"Hello {user.email},\n\n"
                    f"Please verify your email address by clicking the link below:\n"
                    f"{verify_url}\n\n"
                    f"Thank you,\n{settings.APP_NAME} Team"
                )

                from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER

                logger.info(f"Attempting to send verification email to {user.email} (attempt {attempt + 1}/{max_retries})")
                logger.debug(f"From: {from_email}, Subject: {subject}")
                
                result = send_mail(
                    subject=subject,
                    message=plain_message,
                    html_message=html_message,
                    from_email=from_email,
                    recipient_list=[user.email],
                    fail_silently=False,
                )

                logger.info(f"Verification email sent to {user.email}, result: {result}")
                return True

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error sending verification email to {user.email} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                else:
                    logger.error(f"Failed to send verification email to {user.email} after {max_retries} attempts: {str(e)}")
                    logger.error(traceback.format_exc())
                raise

    @staticmethod
    def send_password_reset_email(user):
        """Send password reset email to user with reset link"""
        try:    
            # Generate verification token for link
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            # Create verification link
            reset_url = f"{settings.FRONTEND_URL}/password-reset?uid={uid}&token={token}"

            subject = f"{settings.APP_NAME} - Reset your Password"

            context = {
                'user': user,
                'reset_url': reset_url,
                'app_name': settings.APP_NAME,
            }

            html_message = render_to_string('emails/password_reset.html', context)

            plain_message = f"""
                                Hello {user.email},

                                You requested to reset your password for your {settings.APP_NAME} account.
                                Please click the link below to reset your password:

                                {reset_url}

                                If you didn't request this, please ignore this email.

                                Thank you,
                                {settings.APP_NAME} Team
                            """

            # Send email
            from_email = settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER

            logger.info(f"Attempting to send password reset email to {user.email}")
            logger.debug(f"From: {from_email}, Subject: {subject}")

            result = send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=from_email,
                recipient_list=[user.email],
                fail_silently=False,
            )

            logger.info(f"Password reset email sent to {user.email}, result: {result}")
            return True
        
        except Exception as e:
            logger.error(f"Error sending password reset email: {user.email}: {str(e)}")
            logger.error(traceback.format_exc())
            raise e