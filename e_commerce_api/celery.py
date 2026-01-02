import os
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


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')