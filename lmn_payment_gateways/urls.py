"""
Main URL configuration for Lumenario Payment Gateway.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


# API URL patterns
api_patterns = [
    # API Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Health check
    path('', include('core.urls')),

    # Client management
    path('clients/', include('clients.urls')),

    # MPesa payments
    path('payments/', include('mpesa.urls')),

    # Versioned API (alternative structure)
    path('v1/clients/', include('clients.urls')),
    path('v1/mpesa/', include('mpesa.api.v1.urls')),
]

urlpatterns = [
    # Admin panel
    path('admin/', admin.site.urls),

    # API routes
    path('api/', include(api_patterns)),

    # Root redirect to API docs
    path('', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom error handlers
handler400 = 'core.views.bad_request'
handler403 = 'core.views.permission_denied'
handler404 = 'core.views.not_found'
handler500 = 'core.views.server_error'
