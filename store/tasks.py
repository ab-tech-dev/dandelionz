import logging
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import Product
from users.models import Vendor

logger = logging.getLogger("store.tasks")


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
    name="store.send_product_approval_email"
)
def send_product_approval_email_task(self, product_id: int):
    """
    Celery task to send product approval notification to vendor
    """
    try:
        product = Product.objects.select_related('store', 'store__user').get(id=product_id)
        vendor = product.store
        
        logger.info(f"[ProductApprovalTask] Sending approval email for product: {product.name} to vendor: {vendor.user.email}")
        
        # Prepare email context
        context = {
            'vendor_name': vendor.store_name,
            'product_name': product.name,
            'product_id': product.id,
            'product_slug': product.slug,
            'approval_status': 'APPROVED',
            'message': 'Your product has been approved and is now visible to customers.'
        }
        
        # Render HTML email
        html_message = render_to_string('emails/product_approval.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        send_mail(
            subject=f"Product Approved: {product.name}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[vendor.user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"[ProductApprovalTask] Approval email sent successfully to {vendor.user.email}")
        return {"status": "success", "email": vendor.user.email, "product_id": product_id}
        
    except Product.DoesNotExist:
        logger.warning(f"[ProductApprovalTask] Product with id {product_id} not found.")
        return {"status": "failed", "reason": "product_not_found"}
        
    except Exception as e:
        logger.error(
            f"[ProductApprovalTask] Failed for product {product_id} "
            f"(attempt {self.request.retries}): {str(e)}"
        )
        raise self.retry(exc=e)


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
    name="store.send_product_rejection_email"
)
def send_product_rejection_email_task(self, product_id: int, rejection_reason: str = ""):
    """
    Celery task to send product rejection notification to vendor with reason
    """
    try:
        product = Product.objects.select_related('store', 'store__user').get(id=product_id)
        vendor = product.store
        
        logger.info(f"[ProductRejectionTask] Sending rejection email for product: {product.name} to vendor: {vendor.user.email}")
        
        # Prepare email context
        context = {
            'vendor_name': vendor.store_name,
            'product_name': product.name,
            'product_id': product.id,
            'product_slug': product.slug,
            'approval_status': 'REJECTED',
            'rejection_reason': rejection_reason,
            'message': 'Your product has been rejected. Please review the reason below and resubmit if needed.'
        }
        
        # Render HTML email
        html_message = render_to_string('emails/product_rejection.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        send_mail(
            subject=f"Product Rejected: {product.name}",
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[vendor.user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"[ProductRejectionTask] Rejection email sent successfully to {vendor.user.email}")
        return {"status": "success", "email": vendor.user.email, "product_id": product_id}
        
    except Product.DoesNotExist:
        logger.warning(f"[ProductRejectionTask] Product with id {product_id} not found.")
        return {"status": "failed", "reason": "product_not_found"}
        
    except Exception as e:
        logger.error(
            f"[ProductRejectionTask] Failed for product {product_id} "
            f"(attempt {self.request.retries}): {str(e)}"
        )
        raise self.retry(exc=e)
