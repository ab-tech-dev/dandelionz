from django.apps import AppConfig


class StoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "store"

    def ready(self):
        """
        Register signal handlers when the app is ready.
        This ensures approval logging is enabled.
        """
        import store.signals  # noqa

