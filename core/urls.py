"""
Core URL patterns for health checks and utility endpoints.
"""

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.health_check, name='health-check'),
    path('status/', views.system_status, name='system-status'),
]
