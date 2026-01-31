
from users.consumer import NotificationConsumer
from django.urls import re_path


websocket_urlpatterns = [
    re_path(r'ws/notifications/$', NotificationConsumer.as_asgi()),
]