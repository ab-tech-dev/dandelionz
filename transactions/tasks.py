import logging
from celery import shared_task
from celery.schedules import crontab
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

from .models import Order, TransactionLog
from users.models import Notification
from authentication.models import CustomUser

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="transactions.check_overdue_deliveries"
)
def check_overdue_deliveries():
    """
    Periodic task to check for orders that have been SHIPPED for more than 30 days.
    Creates escalation tickets and notifies admins.
    
    Runs daily at midnight (00:00) by default.
    Configure in CELERY_BEAT_SCHEDULE in settings.py:
    
    'check_overdue_deliveries': {
        'task': 'transactions.check_overdue_deliveries',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
    },
    """
    try:
        threshold_date = timezone.now() - timedelta(days=30)
        
        # Find orders that have been SHIPPED for more than 30 days
        overdue_orders = Order.objects.filter(
            status=Order.Status.SHIPPED,
            shipped_at__lt=threshold_date,
            shipped_at__isnull=False
        ).select_related('customer', 'delivery_agent')
        
        overdue_count = overdue_orders.count()
        
        if overdue_count == 0:
            logger.info("No overdue deliveries found")
            return {"status": "success", "overdue_count": 0}
        
        logger.warning(f"Found {overdue_count} overdue deliveries (SHIPPED > 30 days)")
        
        # Get admin users for notification
        admin_users = CustomUser.objects.filter(is_staff=True, is_superuser=True)
        
        # Process each overdue order
        for order in overdue_orders:
            days_shipped = (timezone.now() - order.shipped_at).days
            
            # Create transaction log for tracking
            TransactionLog.objects.create(
                order=order,
                action=TransactionLog.Action.OTHER,
                level=TransactionLog.Level.WARNING,
                message=f"Order {order.order_id} has been SHIPPED for {days_shipped} days without delivery. Requires escalation.",
                related_user=order.customer,
                metadata={
                    "days_overdue": days_shipped,
                    "shipped_at": order.shipped_at.isoformat(),
                    "customer_email": order.customer.email,
                    "delivery_agent": order.delivery_agent.user.email if order.delivery_agent else None,
                }
            )
            
            logger.warning(
                f"Overdue order {order.order_id}: Shipped {days_shipped} days ago, "
                f"Customer: {order.customer.email}, "
                f"Delivery Agent: {order.delivery_agent.user.email if order.delivery_agent else 'Not assigned'}"
            )
            
            # Notify admin users about overdue delivery
            for admin in admin_users:
                Notification.objects.create(
                    recipient=admin,
                    title=f"Overdue Delivery Alert: Order {order.order_id}",
                    message=f"Order {order.order_id} has been in SHIPPED status for {days_shipped} days. "
                            f"Customer: {order.customer.email}. "
                            f"Delivery Agent: {order.delivery_agent.user.email if order.delivery_agent else 'Not assigned'}. "
                            f"Please investigate and take appropriate action.",
                    is_read=False
                )
            
            # Optional: Send email notification to admin
            if admin_users.exists():
                admin_emails = list(admin_users.values_list('email', flat=True))
                try:
                    context = {
                        'order_id': str(order.order_id),
                        'days_overdue': days_shipped,
                        'customer_name': order.customer.get_full_name() or order.customer.email,
                        'customer_email': order.customer.email,
                        'shipped_date': order.shipped_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'delivery_agent': order.delivery_agent.user.email if order.delivery_agent else 'Not assigned',
                    }
                    
                    html_message = render_to_string('emails/overdue_delivery_alert.html', context)
                    plain_message = strip_tags(html_message)
                    
                    send_mail(
                        subject=f"URGENT: Overdue Delivery Alert - Order {order.order_id}",
                        message=plain_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=admin_emails,
                        html_message=html_message,
                        fail_silently=True,
                    )
                    
                    logger.info(f"Overdue delivery notification email sent to {len(admin_emails)} admins for order {order.order_id}")
                except Exception as e:
                    logger.error(f"Failed to send overdue delivery email for order {order.order_id}: {str(e)}")
        
        return {
            "status": "success",
            "overdue_count": overdue_count,
            "processed": True,
            "message": f"Processed {overdue_count} overdue deliveries"
        }
    
    except Exception as e:
        logger.error(f"Error in check_overdue_deliveries task: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={
        'max_retries': 5,
        'countdown': 60,
    },
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    name="transactions.send_delivery_escalation_email"
)
def send_delivery_escalation_email(self, order_id):
    """
    Send email notification to admin and delivery agent about overdue delivery.
    Called by the periodic check_overdue_deliveries task or manually.
    """
    try:
        order = Order.objects.select_related('customer', 'delivery_agent').get(order_id=order_id)
        
        logger.info(f"Sending escalation email for order {order_id}")
        
        # Get admin users
        admin_users = CustomUser.objects.filter(is_staff=True, is_superuser=True)
        admin_emails = list(admin_users.values_list('email', flat=True))
        
        days_shipped = (timezone.now() - order.shipped_at).days if order.shipped_at else 0
        
        context = {
            'order_id': str(order.order_id),
            'days_overdue': days_shipped,
            'customer_name': order.customer.get_full_name() or order.customer.email,
            'customer_email': order.customer.email,
            'customer_phone': order.customer.phone_number if hasattr(order.customer, 'phone_number') else 'N/A',
            'shipped_date': order.shipped_at.strftime('%Y-%m-%d %H:%M:%S') if order.shipped_at else 'N/A',
            'delivery_agent': order.delivery_agent.user.email if order.delivery_agent else 'Not assigned',
            'delivery_agent_phone': order.delivery_agent.user.phone_number if order.delivery_agent and hasattr(order.delivery_agent.user, 'phone_number') else 'N/A',
        }
        
        html_message = render_to_string('emails/overdue_delivery_alert.html', context)
        plain_message = strip_tags(html_message)
        
        # Send to admins
        if admin_emails:
            send_mail(
                subject=f"URGENT: Overdue Delivery Escalation - Order {order.order_id}",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=admin_emails,
                html_message=html_message,
                fail_silently=False,
            )
            logger.info(f"Escalation email sent to {len(admin_emails)} admins for order {order_id}")
        
        # Optionally send to delivery agent
        if order.delivery_agent:
            agent_email = order.delivery_agent.user.email
            agent_context = context.copy()
            agent_context['is_agent'] = True
            
            agent_html_message = render_to_string('emails/delivery_agent_escalation.html', agent_context)
            agent_plain_message = strip_tags(agent_html_message)
            
            send_mail(
                subject=f"Urgent: Order {order.order_id} Delivery Status Update Required",
                message=agent_plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[agent_email],
                html_message=agent_html_message,
                fail_silently=False,
            )
            logger.info(f"Escalation email sent to delivery agent {agent_email} for order {order_id}")
        
        return {
            "status": "success",
            "order_id": str(order_id),
            "message": "Escalation emails sent successfully"
        }
    
    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for escalation email")
        return {
            "status": "error",
            "error": f"Order {order_id} not found"
        }
    except Exception as e:
        logger.error(f"Error sending delivery escalation email for order {order_id}: {str(e)}", exc_info=True)
        raise
