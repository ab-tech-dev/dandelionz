"""
Referral service for handling referral bonuses and rewards.

This service decouples referral logic from views and provides a clean
interface for processing referral bonuses when users verify their emails.
"""

import logging
from django.conf import settings
from django.db import transaction

from authentication.models import CustomUser, Referral
from transactions.models import Wallet
from users.models import Notification

logger = logging.getLogger(__name__)


class ReferralService:
    """Service class to handle referral-related business logic"""

    @staticmethod
    def get_referral_bonus_amount():
        """Get the configured referral bonus amount"""
        return getattr(settings, 'REFERRAL_BONUS_AMOUNT', 0)

    @staticmethod
    def award_referral_bonuses(user):
        """
        Award referral bonuses for a newly verified user.
        
        Called when a user verifies their email. Processes any pending
        referrals and credits the referrer's wallet.
        
        Args:
            user (CustomUser): The user who just verified their email
            
        Returns:
            dict: Statistics about processed referrals {
                'total_processed': int,
                'total_amount': Decimal,
                'successful': int,
                'failed': int
            }
        """
        if not user or not user.uuid:
            logger.warning("Invalid user object passed to award_referral_bonuses")
            return {'total_processed': 0, 'total_amount': 0, 'successful': 0, 'failed': 0}
        
        stats = {
            'total_processed': 0,
            'total_amount': 0,
            'successful': 0,
            'failed': 0
        }
        
        try:
            # Get unawarded referrals for this newly verified user
            referrals = Referral.objects.filter(
                referred_user=user,
                bonus_awarded=False
            ).select_related('referrer')
            
            stats['total_processed'] = referrals.count()
            
            for referral in referrals:
                try:
                    with transaction.atomic():
                        # Mark bonus as awarded
                        referral.bonus_awarded = True
                        referral.save(update_fields=['bonus_awarded'])
                        logger.info(f"Marked referral bonus as awarded for {referral.referrer.email}")
                        
                        # Credit bonus to referrer's wallet
                        referrer = referral.referrer
                        wallet, created = Wallet.objects.get_or_create(user=referrer)
                        wallet.credit(
                            referral.bonus_amount,
                            source=f"Referral bonus for {user.email}"
                        )
                        logger.info(f"Credited {referral.bonus_amount} to {referrer.email}'s wallet")
                        
                        # Create notification for referrer
                        Notification.objects.create(
                            recipient=referrer,
                            title="Referral Bonus Credited",
                            message=f"You have received a referral bonus of {referral.bonus_amount} "
                                    f"for referring {user.email}.",
                        )
                        logger.info(f"Referral bonus awarded and notification sent to {referrer.email}")
                        
                        stats['total_amount'] += referral.bonus_amount
                        stats['successful'] += 1
                        
                except Exception as bonus_error:
                    logger.error(f"Error processing referral {referral.id}: {str(bonus_error)}")
                    stats['failed'] += 1
                    # Continue processing other referrals if one fails
                    continue
            
            return stats
            
        except Exception as referral_error:
            logger.error(f"Error awarding referral bonuses: {str(referral_error)}")
            return stats

    @staticmethod
    def create_referral(referrer_email, referred_user):
        """
        Create a referral relationship.
        
        Args:
            referrer_email (str): Email of the user who referred
            referred_user (CustomUser): The newly referred user
            
        Returns:
            tuple: (success: bool, referral: Referral or None, message: str)
        """
        if not referrer_email or not referred_user:
            return False, None, "Invalid parameters"
        
        try:
            referrer = CustomUser.objects.get(referral_code=referrer_email)
            bonus_amount = ReferralService.get_referral_bonus_amount()
            
            referral = Referral.objects.create(
                referrer=referrer,
                referred_user=referred_user,
                bonus_amount=bonus_amount,
                bonus_awarded=False
            )
            
            logger.info(f"Referral created: {referrer.email} referred {referred_user.email}")
            return True, referral, f"Referral registered. Bonus of {bonus_amount} will be awarded when they verify their email."
            
        except CustomUser.DoesNotExist:
            logger.warning(f"Invalid referral code used: {referrer_email}")
            return False, None, "Invalid referral code"
        except Exception as e:
            logger.error(f"Error creating referral: {str(e)}")
            return False, None, "Failed to process referral"

    @staticmethod
    def get_user_referrals(user):
        """
        Get all referrals made by a user.
        
        Args:
            user (CustomUser): The referrer user
            
        Returns:
            QuerySet: Referral objects made by this user
        """
        return Referral.objects.filter(referrer=user).select_related('referred_user')

    @staticmethod
    def get_referral_stats(user):
        """
        Get referral statistics for a user.
        
        Args:
            user (CustomUser): The user to get stats for
            
        Returns:
            dict: Statistics about their referrals {
                'total_referrals': int,
                'successful_referrals': int,
                'total_bonus_awarded': Decimal,
                'pending_bonus': Decimal
            }
        """
        referrals = Referral.objects.filter(referrer=user)
        
        awarded = referrals.filter(bonus_awarded=True)
        pending = referrals.filter(bonus_awarded=False)
        
        return {
            'total_referrals': referrals.count(),
            'successful_referrals': awarded.count(),
            'total_bonus_awarded': sum(r.bonus_amount for r in awarded) or 0,
            'pending_bonus': sum(r.bonus_amount for r in pending) or 0
        }
