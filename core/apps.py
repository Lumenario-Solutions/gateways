from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        """Import signals when the app is ready."""
        try:
            import core.signals  # noqa
            print("Core signals loaded successfully")
        except ImportError as e:
            print(f"Failed to load core signals: {e}")
