
import time
import logging
import uuid
from datetime import timedelta
from typing import Optional, Dict, Any

from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import (
    api_view,
    permission_classes,
    action
)
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from clients.models import Client
from clients.permissions.api_client_permissions import IsValidClient
from core.models import ClientEnvironmentVariable, Notification
from core.utils.notification_service import send_notification, notify_credentials_updated

from .models import ActivityLog
from .serializers import (
    ActivityLogSerializer,
    ActivityLogListSerializer,
    ActivityLogStatsSerializer,
    NotificationSerializer,
    ClientEnvironmentVariableSerializer
)



class ActivityLogFilter(django_filters.FilterSet):
    """
    Filter class for ActivityLog model.
    """

    # Date range filters
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    date_range = django_filters.CharFilter(method='filter_date_range')

    # Activity type filters
    activity_types = django_filters.CharFilter(method='filter_activity_types')
    exclude_activity_types = django_filters.CharFilter(method='filter_exclude_activity_types')

    # Level filters
    levels = django_filters.CharFilter(method='filter_levels')
    min_level = django_filters.CharFilter(method='filter_min_level')

    # Client and user filters
    client_name = django_filters.CharFilter(field_name='client__name', lookup_expr='icontains')
    username = django_filters.CharFilter(field_name='user__username', lookup_expr='icontains')

    # Duration filters
    min_duration = django_filters.NumberFilter(field_name='duration_ms', lookup_expr='gte')
    max_duration = django_filters.NumberFilter(field_name='duration_ms', lookup_expr='lte')

    # Error filters
    has_error = django_filters.BooleanFilter(method='filter_has_error')

    class Meta:
        model = ActivityLog
        fields = [
            'activity_type', 'level', 'client', 'user', 'ip_address',
            'created_after', 'created_before', 'date_range',
            'activity_types', 'exclude_activity_types',
            'levels', 'min_level',
            'client_name', 'username',
            'min_duration', 'max_duration',
            'has_error'
        ]

    def filter_date_range(self, queryset, name, value):
        """Filter by predefined date ranges."""
        now = timezone.now()

        if value == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return queryset.filter(created_at__gte=start)
        elif value == 'yesterday':
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            return queryset.filter(created_at__gte=start, created_at__lt=end)
        elif value == 'last_24h':
            start = now - timedelta(hours=24)
            return queryset.filter(created_at__gte=start)
        elif value == 'last_7d':
            start = now - timedelta(days=7)
            return queryset.filter(created_at__gte=start)
        elif value == 'last_30d':
            start = now - timedelta(days=30)
            return queryset.filter(created_at__gte=start)

        return queryset

    def filter_activity_types(self, queryset, name, value):
        """Filter by multiple activity types (comma-separated)."""
        types = [t.strip() for t in value.split(',') if t.strip()]
        if types:
            return queryset.filter(activity_type__in=types)
        return queryset

    def filter_exclude_activity_types(self, queryset, name, value):
        """Exclude multiple activity types (comma-separated)."""
        types = [t.strip() for t in value.split(',') if t.strip()]
        if types:
            return queryset.exclude(activity_type__in=types)
        return queryset

    def filter_levels(self, queryset, name, value):
        """Filter by multiple levels (comma-separated)."""
        levels = [l.strip() for l in value.split(',') if l.strip()]
        if levels:
            return queryset.filter(level__in=levels)
        return queryset

    def filter_min_level(self, queryset, name, value):
        """Filter by minimum log level."""
        level_order = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
        min_order = level_order.get(value.upper())

        if min_order is not None:
            allowed_levels = [level for level, order in level_order.items() if order >= min_order]
            return queryset.filter(level__in=allowed_levels)

        return queryset

    def filter_has_error(self, queryset, name, value):
        """Filter logs that have error messages."""
        if value:
            return queryset.exclude(error_message='')
        else:
            return queryset.filter(error_message='')


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for ActivityLog model.

    Provides list and retrieve actions with comprehensive filtering,
    searching, and ordering capabilities.
    """

    queryset = ActivityLog.objects.all()
    permission_classes = [IsValidClient]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ActivityLogFilter
    search_fields = [
        'description', 'error_message', 'activity_type',
        'client__name', 'user__username', 'ip_address'
    ]
    ordering_fields = [
        'created_at', 'activity_type', 'level', 'duration_ms'
    ]
    ordering = ['-created_at']  # Default ordering

    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        Use simplified serializer for list view for better performance.
        """
        if self.action == 'list':
            return ActivityLogListSerializer
        return ActivityLogSerializer

    def get_queryset(self):
        """
        Optimize queryset with select_related for better performance.
        """
        queryset = super().get_queryset()

        # Optimize with select_related
        queryset = queryset.select_related('client', 'user')

        # Filter by client if user has limited access
        user = self.request.user
        if hasattr(user, 'client') and user.client:
            # If user is associated with a specific client, filter logs
            queryset = queryset.filter(client=user.client)

        return queryset

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get activity log statistics.

        Returns comprehensive statistics about activity logs including:
        - Total counts
        - Recent activity counts
        - Top activity types
        - Activity distribution by level
        - Hourly distribution
        """
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        # Get base queryset (filtered by client if applicable)
        base_queryset = self.get_queryset()

        # Basic counts
        total_logs = base_queryset.count()
        logs_last_24h = base_queryset.filter(created_at__gte=last_24h).count()
        logs_last_7d = base_queryset.filter(created_at__gte=last_7d).count()

        # Error and warning counts
        recent_logs = base_queryset.filter(created_at__gte=last_24h)
        error_logs_last_24h = recent_logs.filter(level__in=['ERROR', 'CRITICAL']).count()
        warning_logs_last_24h = recent_logs.filter(level='WARNING').count()

        # Payment activity count
        payment_activities_last_24h = recent_logs.filter(
            activity_type__startswith='PAYMENT'
        ).count()

        # Top activity types (last 24h)
        top_activity_types = list(
            recent_logs.values('activity_type')
            .annotate(count=Count('activity_type'))
            .order_by('-count')[:10]
        )

        # Top clients (last 24h)
        top_clients = list(
            recent_logs.filter(client__isnull=False)
            .values('client__name', 'client__client_id')
            .annotate(count=Count('client'))
            .order_by('-count')[:10]
        )

        # Activity by level
        activity_by_level = dict(
            recent_logs.values('level')
            .annotate(count=Count('level'))
            .values_list('level', 'count')
        )

        # Hourly distribution (last 24 hours)
        hourly_data = []
        for i in range(24):
            hour_start = last_24h + timedelta(hours=i)
            hour_end = hour_start + timedelta(hours=1)
            hour_count = base_queryset.filter(
                created_at__gte=hour_start,
                created_at__lt=hour_end
            ).count()

            hourly_data.append({
                'hour': hour_start.strftime('%H:00'),
                'timestamp': hour_start.isoformat(),
                'count': hour_count
            })

        stats_data = {
            'total_logs': total_logs,
            'logs_last_24h': logs_last_24h,
            'logs_last_7d': logs_last_7d,
            'error_logs_last_24h': error_logs_last_24h,
            'warning_logs_last_24h': warning_logs_last_24h,
            'payment_activities_last_24h': payment_activities_last_24h,
            'top_activity_types': top_activity_types,
            'top_clients': top_clients,
            'activity_by_level': activity_by_level,
            'hourly_distribution': hourly_data
        }

        serializer = ActivityLogStatsSerializer(stats_data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Export activity logs as CSV.
        Applies current filters and returns CSV data.
        """
        import csv
        import io
        from django.http import HttpResponse

        # Get filtered queryset
        queryset = self.filter_queryset(self.get_queryset())

        # Limit export size to prevent memory issues
        max_export_size = 10000
        if queryset.count() > max_export_size:
            return Response(
                {'error': f'Export size limited to {max_export_size} records. Please apply filters to reduce the dataset.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="activity_logs_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)

        # Write header
        writer.writerow([
            'Log ID', 'Activity Type', 'Description', 'Level', 'Client', 'User',
            'IP Address', 'Duration (ms)', 'Error Message', 'Created At'
        ])

        # Write data
        for log in queryset.select_related('client', 'user'):
            writer.writerow([
                str(log.log_id),
                log.activity_type,
                log.description,
                log.level,
                log.client.name if log.client else '',
                log.user.username if log.user else '',
                log.ip_address or '',
                log.duration_ms or '',
                log.error_message or '',
                log.created_at.isoformat()
            ])

        return response


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for Notification model.
    """

    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsValidClient]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'notification_type', 'status', 'is_read', 'email_sent', 'whatsapp_sent'
    ]
    search_fields = ['title', 'message', 'client__name']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter by client if user has limited access."""
        queryset = super().get_queryset()
        queryset = queryset.select_related('client')

        user = self.request.user
        if hasattr(user, 'client') and user.client:
            queryset = queryset.filter(client=user.client)

        return queryset


class ClientEnvironmentVariableViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for ClientEnvironmentVariable model.
    Note: Encrypted values are not exposed for security.
    """

    queryset = ClientEnvironmentVariable.objects.all()
    serializer_class = ClientEnvironmentVariableSerializer
    permission_classes = [IsValidClient]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['variable_type', 'is_active']
    search_fields = ['client__name', 'variable_type', 'custom_name', 'description']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter by client if user has limited access."""
        queryset = super().get_queryset()
        queryset = queryset.select_related('client')

        user = self.request.user
        if hasattr(user, 'client') and user.client:
            queryset = queryset.filter(client=user.client)

        return queryset


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint.

    Returns basic health status without detailed information.
    """
    try:
        # Quick database check
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        return JsonResponse({
            'status': 'healthy',
            'timestamp': time.time(),
            'version': '1.0.0'
        })

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': 'Database connection failed',
            'timestamp': time.time()
        }, status=503)


@api_view(['GET'])
@permission_classes([AllowAny])
def system_status(request):
    """
    Detailed system status check.

    Returns comprehensive system health information.
    """
    try:
        status_data = {
            'status': 'healthy',
            'timestamp': time.time(),
            'version': '1.0.0',
            'environment': getattr(settings, 'ENVIRONMENT', 'development'),
            'services': {}
        }

        # Database check
        try:
            start_time = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                migration_count = cursor.fetchone()[0]

            db_time = (time.time() - start_time) * 1000
            status_data['services']['database'] = {
                'status': 'healthy',
                'response_time_ms': round(db_time, 2),
                'migrations': migration_count
            }
        except Exception as e:
            status_data['services']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status_data['status'] = 'degraded'

        # Cache check
        try:
            start_time = time.time()
            cache_key = f"health_check_{int(time.time())}"
            cache.set(cache_key, 'test', 1)
            cache.get(cache_key)
            cache.delete(cache_key)

            cache_time = (time.time() - start_time) * 1000
            status_data['services']['cache'] = {
                'status': 'healthy',
                'response_time_ms': round(cache_time, 2)
            }
        except Exception as e:
            status_data['services']['cache'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status_data['status'] = 'degraded'

        # MPesa service check
        try:
            from mpesa.mpesa_client import get_mpesa_client

            start_time = time.time()
            client = get_mpesa_client('sandbox')
            test_result = client.test_connection()

            mpesa_time = (time.time() - start_time) * 1000
            status_data['services']['mpesa'] = {
                'status': 'healthy' if test_result['status'] == 'success' else 'unhealthy',
                'response_time_ms': round(mpesa_time, 2),
                'environment': 'sandbox'
            }

            if test_result['status'] != 'success':
                status_data['services']['mpesa']['error'] = test_result['message']
                status_data['status'] = 'degraded'

        except Exception as e:
            status_data['services']['mpesa'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            status_data['status'] = 'degraded'

        # Set overall status
        unhealthy_services = [
            service for service in status_data['services'].values()
            if service['status'] == 'unhealthy'
        ]

        if unhealthy_services:
            status_data['status'] = 'unhealthy'

        http_status = 200 if status_data['status'] == 'healthy' else 503

        return JsonResponse(status_data, status=http_status)

    except Exception as e:
        logger.error(f"System status check failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': 'System status check failed',
            'timestamp': time.time()
        }, status=503)


# Error handlers
def bad_request(request, exception=None):
    """Handle 400 Bad Request errors."""
    return JsonResponse({
        'error': True,
        'message': 'Bad Request',
        'code': 'BAD_REQUEST',
        'status_code': 400
    }, status=400)


def permission_denied(request, exception=None):
    """Handle 403 Permission Denied errors."""
    return JsonResponse({
        'error': True,
        'message': 'Permission Denied',
        'code': 'PERMISSION_DENIED',
        'status_code': 403
    }, status=403)


def not_found(request, exception=None):
    """Handle 404 Not Found errors."""
    return JsonResponse({
        'error': True,
        'message': 'Resource Not Found',
        'code': 'NOT_FOUND',
        'status_code': 404
    }, status=404)


def server_error(request):
    """Handle 500 Internal Server Error."""
    return JsonResponse({
        'error': True,
        'message': 'Internal Server Error',
        'code': 'INTERNAL_ERROR',
        'status_code': 500
    }, status=500)
