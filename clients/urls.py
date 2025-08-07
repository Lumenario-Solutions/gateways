"""
Client management URL patterns.
"""

from django.urls import path
from . import views

app_name = 'clients'

urlpatterns = [
    # Client registration and profile
    path('register/', views.ClientRegistrationView.as_view(), name='client-register'),
    path('profile/', views.ClientProfileView.as_view(), name='client-profile'),

    # API key management
    path('api-keys/', views.APIKeyManagementView.as_view(), name='api-keys'),
    path('api-keys/<str:api_key>/', views.APIKeyDetailView.as_view(), name='api-key-detail'),

    # Configuration
    path('configuration/', views.ClientConfigurationView.as_view(), name='client-configuration'),

    # Statistics and analytics
    path('stats/', views.ClientStatsView.as_view(), name='client-stats'),
    path('transactions/', views.client_transactions, name='client-transactions'),

    # Security
    path('ip-whitelist/', views.IPWhitelistView.as_view(), name='ip-whitelist'),

    # Webhook testing
    path('test-webhook/', views.WebhookTestView.as_view(), name='test-webhook'),
]
