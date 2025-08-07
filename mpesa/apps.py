from django.apps import AppConfig

class MpesaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mpesa'

    # def ready(self):
    #     # Safe import point for model-related stuff
    #     from .mpesa_client import MpesaClient

    #     # Optional: you can initialize or test here
    #     client = MpesaClient()
    #     client.load_credentials()
