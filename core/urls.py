"""
URL configuration for core app - activity logs and monitoring endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for ViewSets
router = DefaultRouter()
router.register(r'activity-logs', views.ActivityLogViewSet, basename='activitylog')
router.register(r'notifications', views.NotificationViewSet, basename='notification')
router.register(r'environment-variables', views.ClientEnvironmentVariableViewSet, basename='clientenvironmentvariable')
router.register(r'templates', views.ClientTemplateViewSet, basename='clienttemplate')

app_name = 'core'

urlpatterns = [
    # Include ViewSet URLs
    path('', include(router.urls)),

    # Custom endpoints for activity logs
    path('activity-logs/stats/', views.ActivityLogViewSet.as_view({'get': 'stats'}), name='activity-logs-stats'),
    path('activity-logs/export/', views.ActivityLogViewSet.as_view({'get': 'export'}), name='activity-logs-export'),
]

# URL patterns with descriptions:
#
# Activity Logs (Read-only):
# GET /api/v1/core/activity-logs/                     - List all activity logs with filtering
# GET /api/v1/core/activity-logs/{log_id}/            - Retrieve specific activity log
# GET /api/v1/core/activity-logs/stats/               - Get activity log statistics
# GET /api/v1/core/activity-logs/export/              - Export activity logs as CSV
#
# Available filters for activity logs:
# - activity_type: Filter by activity type
# - level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
# - client: Filter by client ID
# - user: Filter by user ID
# - ip_address: Filter by IP address
# - created_after: Filter logs created after this date
# - created_before: Filter logs created before this date
# - date_range: Predefined ranges (today, yesterday, last_24h, last_7d, last_30d)
# - activity_types: Multiple activity types (comma-separated)
# - exclude_activity_types: Exclude activity types (comma-separated)
# - levels: Multiple levels (comma-separated)
# - min_level: Minimum log level
# - client_name: Filter by client name (case-insensitive contains)
# - username: Filter by username (case-insensitive contains)
# - min_duration: Minimum duration in milliseconds
# - max_duration: Maximum duration in milliseconds
# - has_error: Filter logs with/without error messages (true/false)
#
# Search fields: description, error_message, activity_type, client__name, user__username, ip_address
# Ordering fields: created_at, activity_type, level, duration_ms
#
# Notifications (Read-only):
# GET /api/v1/core/notifications/                     - List all notifications
# GET /api/v1/core/notifications/{notification_id}/   - Retrieve specific notification
#
# Environment Variables (Read-only):
# GET /api/v1/core/environment-variables/             - List environment variables (values encrypted)
# GET /api/v1/core/environment-variables/{env_id}/    - Retrieve specific environment variable
#
# Example API calls:
#
# 1. Get recent error logs:
# GET /api/v1/core/activity-logs/?level=ERROR&date_range=last_24h
#
# 2. Get payment-related activities:
# GET /api/v1/core/activity-logs/?activity_types=PAYMENT_INITIATED,PAYMENT_SUCCESSFUL,PAYMENT_FAILED
#
# 3. Search for specific client activities:
# GET /api/v1/core/activity-logs/?client_name=TestClient&search=transaction
#
# 4. Get activity statistics:
# GET /api/v1/core/activity-logs/stats/
#
# 5. Export filtered logs:
# GET /api/v1/core/activity-logs/export/?level=ERROR&date_range=last_7d
#
# 6. Get logs with pagination:
# GET /api/v1/core/activity-logs/?page=1&page_size=50
#
# 7. Get logs ordered by duration:
# GET /api/v1/core/activity-logs/?ordering=-duration_ms
#
# Response format for activity logs:
# {
#   "count": 150,
#   "next": "http://api/v1/core/activity-logs/?page=2",
#   "previous": null,
#   "results": [
#     {
#       "log_id": "uuid-here",
#       "activity_type": "PAYMENT_SUCCESSFUL",
#       "activity_type_display": "Payment Successful",
#       "description": "Payment successful: KES 1000.00",
#       "level": "INFO",
#       "level_display": "Info",
#       "client": {
#         "client_id": "uuid-here",
#         "name": "Test Client",
#         "email": "client@example.com",
#         "status": "active",
#         "plan": "basic"
#       },
#       "user": {
#         "id": 1,
#         "username": "admin",
#         "first_name": "Admin",
#         "last_name": "User",
#         "email": "admin@example.com"
#       },
#       "ip_address": "192.168.1.1",
#       "user_agent": "Mozilla/5.0...",
#       "metadata": {
#         "transaction_id": "uuid-here",
#         "amount": "1000.00",
#         "phone_number": "254712345678"
#       },
#       "error_message": "",
#       "duration_ms": 250,
#       "duration_display": "250ms",
#       "created_at": "2025-01-14T10:30:00Z",
#       "is_error": false,
#       "is_security_related": false
#     }
#   ]
# }
