"""
MPesa URL patterns for payment processing endpoints.
"""

from django.urls import path, include

app_name = 'mpesa'

urlpatterns = [
    # Version 1 API
    path('v1/', include('mpesa.api.v1.urls')),

    # Default to latest version
    path('', include('mpesa.api.v1.urls')),
]
