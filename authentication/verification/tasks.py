import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from .emails import EmailService

User = get_user_model()
logger = logging.getLogger("authentication.verification")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={
        'max_retries': 5,
        'countdown': 60,  # Wait 60 seconds before first retry
    },
    retry_backoff=True,
    retry_backoff_max=300,  # Max 5 minute backoff
    retry_jitter=True,
    name="authentication.verification.send_verification_email"
)
def send_verification_email_task(self, user_uuid: int):
    """Celery task to send verification email with improved retry logic"""
    try:
        user = User.objects.get(uuid=user_uuid)
        if not user.is_verified:
            logger.info(f"[VerificationEmailTask] Sending verification email to: {user.email}")
            EmailService.send_verification_email(user)
            return {"status": "success", "email": user.email, "user_uuid": str(user.uuid)}
        else:
            logger.info(f"[VerificationEmailTask] Skipped: user already verified ({user.email})")
            return {"status": "skipped", "reason": "already_verified"}

    except User.DoesNotExist:
        logger.warning(f"[VerificationEmailTask] User with uuid {user_uuid} not found.")
        return {"status": "failed", "reason": "user_not_found"}

    except Exception as e:
        logger.error(
            f"[VerificationEmailTask] Failed for user {user_uuid} "
            f"(attempt {self.request.retries}): {str(e)}"
        )
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={
        'max_retries': 5,
        'countdown': 60,  # Wait 60 seconds before first retry
    },
    retry_backoff=True,
    retry_backoff_max=300,  # Max 5 minute backoff
    retry_jitter=True,
    name="authentication.verification.send_password_reset_email"
)
def send_password_reset_email_task(self, user_uuid: int):
    """Celery task to send password reset email with improved retry logic"""
    try:
        user = User.objects.get(uuid=user_uuid)
        if user.is_verified:
            logger.info(f"[PasswordResetTask] Sending password reset email to: {user.email}")
            EmailService.send_password_reset_email(user)
            return {"status": "success", "email": user.email, "user_uuid": str(user.uuid)}
        else:
            logger.warning(f"[PasswordResetTask] Skipped: unverified user {user.email}")
            return {"status": "skipped", "reason": "user_not_verified"}

    except User.DoesNotExist:
        logger.warning(f"[PasswordResetTask] User with uuid {user_uuid} not found.")
        return {"status": "failed", "reason": "user_not_found"}

    except Exception as e:
        logger.error(
            f"[PasswordResetTask] Failed for user {user_uuid} "
            f"(attempt {self.request.retries}): {str(e)}"
        )
        raise self.retry(exc=e)
