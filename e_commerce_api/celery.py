import os
import logging
from celery import Celery
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_commerce_api.settings')

broker_url = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
backend_url = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')

app = Celery(
    "e_commerce_api",
    broker=broker_url,
    backend=backend_url
)

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Configure Celery logging
logger = logging.getLogger(__name__)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# Signal handlers for task lifecycle logging
from celery.signals import before_task_publish, task_prerun, task_postrun, task_failure

@before_task_publish.connect(sender='*')
def task_before_publish(sender=None, body=None, **kwargs):
    """Log task before it's published to the broker"""
    logger.debug(f"Task {sender} queued for execution")


@task_prerun.connect
def task_on_prerun(sender=None, task_id=None, task=None, **kwargs):
    """Log task before execution starts"""
    logger.info(f"[CELERY] Task {task.name} (ID: {task_id}) STARTING")


@task_postrun.connect
def task_on_postrun(sender=None, task_id=None, task=None, result=None, **kwargs):
    """Log task after successful execution"""
    logger.info(f"[CELERY] Task {task.name} (ID: {task_id}) COMPLETED - Result: {result}")


@task_failure.connect
def task_on_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Log task failures"""
    logger.error(f"[CELERY] Task {sender} (ID: {task_id}) FAILED - Exception: {exception}", exc_info=True)
