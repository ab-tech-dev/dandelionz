import logging
import traceback
import os
from django.conf import settings
from django.core.mail import send_mail
import base64

from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model


User = get_user_model()
logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending user-related emails"""

    @staticmethod
    def get_logo_base64():
        """Get base64 encoded logo with proper error handling"""
        try:
            # Use absolute path - adjust this to your project structure
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'logo', 'Dandelion.png')
            
            # Alternative: if logo is in the same directory as this file
            # logo_path = os.path.join(os.path.dirname(__file__), 'Dandelion.png')
            
            if not os.path.exists(logo_path):
                logger.warning(f"Logo not found at {logo_path}")
                return None
                
            with open(logo_path, 'rb') as image_file:
                encoded = base64.b64encode(image_file.read()).decode('utf-8')
                logger.info(f"Logo encoded successfully, size: {len(encoded)} chars")
                return encoded
        except Exception as e:
            logger.error(f"Error encoding logo: {str(e)}")
            return None

    @staticmethod
    def send_verification_email(user, max_retries=3):
        """Send verification email to user with verification link"""
        for attempt in range(max_retries):
            try:
                # Encode user ID for verification link
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)

                verify_url = f"{settings.FRONTEND_URL}/auth/email-verify?uid={uid}&token={token}"
                
                # Get logo (will be None if file not found)
                logo_base64 = EmailService.get_logo_base64()

                subject = f"{settings.APP_NAME} - Verify Your Email Address"

                context = {
                    'user': user,
                    'verify_url': verify_url,
                    'app_name': settings.APP_NAME,
                    'logo_base64': logo_base64 or '',  # Empty string if logo failed to load
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
            reset_url = f"{settings.FRONTEND_URL}/auth/password-reset-confirm?uid={uid}&token={token}"

            # Get logo
            logo_base64 = EmailService.get_logo_base64()

            subject = f"{settings.APP_NAME} - Reset your Password"

            context = {
                'user': user,
                'reset_url': reset_url,
                'app_name': settings.APP_NAME,
                'logo_base64': logo_base64 or '',
            }

            try:
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

            except Exception as template_error:
                logger.error(f"Template rendering error: {str(template_error)}")
                raise

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