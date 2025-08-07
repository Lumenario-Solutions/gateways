"""
Core views for health checks and error handling.
"""

import time
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


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
            from mpesa.services.mpesa_client import get_mpesa_client

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
