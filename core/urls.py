from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Environment Variables Management
    path('environment-variables/', views.ClientEnvironmentVariableView.as_view(), name='env_variables_list'),
    path('environment-variables/<str:variable_id>/', views.ClientEnvironmentVariableView.as_view(), name='env_variables_detail'),

    # Notifications Management
    path('notifications/', views.NotificationView.as_view(), name='notifications_list'),
    path('notifications/<str:notification_id>/', views.NotificationView.as_view(), name='notifications_detail'),
    path('notifications/<str:notification_id>/<str:action>/', views.NotificationView.as_view(), name='notifications_action'),

    path('health/', views.health_check, name='health-check'),
    path('health/status/', views.system_status, name='system-status'),
]
