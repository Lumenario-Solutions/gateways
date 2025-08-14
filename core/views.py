"""
Core views for health checks and error handling.
"""

import time
import logging
import uuid
from typing import Optional, Dict, Any

from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.request import Request

from clients.permissions.api_client_permissions import IsValidClient
from clients.models import Client
from core.models import ClientEnvironmentVariable, Notification
from core.utils.notification_service import send_notification, notify_credentials_updated

logger = logging.getLogger(__name__)


class ClientEnvironmentVariableView(APIView):
    """
    Manage client environment variables.

    GET /api/v1/core/environment-variables/
    POST /api/v1/core/environment-variables/
    PUT /api/v1/core/environment-variables/<variable_id>/
    DELETE /api/v1/core/environment-variables/<variable_id>/
    """
    permission_classes = [IsValidClient]

    def get(self, request: Request, variable_id: str = None) -> Response:
        """
        Get environment variables for the authenticated client.
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            if variable_id:
                # Get specific variable
                variable = get_object_or_404(
                    ClientEnvironmentVariable,
                    id=variable_id,
                    client=client
                )

                return Response({
                    'success': True,
                    'data': {
                        'id': str(variable.id),
                        'variable_type': variable.variable_type,
                        'custom_name': variable.custom_name,
                        'description': variable.description,
                        'is_active': variable.is_active,
                        'created_at': variable.created_at,
                        'updated_at': variable.updated_at,
                        # Never return the actual value for security
                        'has_value': bool(variable.encrypted_value)
                    },
                    'timestamp': timezone.now()
                }, status=status.HTTP_200_OK)
            else:
                # Get all variables for client
                variables = ClientEnvironmentVariable.objects.filter(
                    client=client
                ).order_by('-created_at')

                # Apply filters
                variable_type = request.query_params.get('type')
                if variable_type:
                    variables = variables.filter(variable_type=variable_type)

                is_active = request.query_params.get('active')
                if is_active is not None:
                    variables = variables.filter(is_active=is_active.lower() == 'true')

                # Pagination
                page_size = min(int(request.query_params.get('page_size', 20)), 100)
                page = int(request.query_params.get('page', 1))
                start = (page - 1) * page_size
                end = start + page_size

                paginated_variables = variables[start:end]
                total_count = variables.count()

                variable_data = []
                for variable in paginated_variables:
                    variable_data.append({
                        'id': str(variable.id),
                        'variable_type': variable.variable_type,
                        'custom_name': variable.custom_name,
                        'description': variable.description,
                        'is_active': variable.is_active,
                        'created_at': variable.created_at,
                        'updated_at': variable.updated_at,
                        'has_value': bool(variable.encrypted_value)
                    })

                return Response({
                    'success': True,
                    'data': {
                        'variables': variable_data,
                        'pagination': {
                            'page': page,
                            'page_size': page_size,
                            'total_count': total_count,
                            'total_pages': (total_count + page_size - 1) // page_size
                        }
                    },
                    'timestamp': timezone.now()
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting environment variables: {e}")
            return Response({
                'error': 'Query failed',
                'message': 'Failed to retrieve environment variables',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request: Request) -> Response:
        """
        Create a new environment variable.
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            data = request.data

            # Validate required fields
            required_fields = ['variable_type', 'variable_value']
            missing_fields = []
            for field in required_fields:
                if field not in data or not data[field]:
                    missing_fields.append(field)

            if missing_fields:
                return Response({
                    'error': 'Missing required fields',
                    'missing_fields': missing_fields,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate variable type
            valid_types = [choice[0] for choice in ClientEnvironmentVariable.ENV_VARIABLE_TYPES]
            if data['variable_type'] not in valid_types:
                return Response({
                    'error': 'Invalid variable type',
                    'message': f"Variable type must be one of: {', '.join(valid_types)}",
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check for existing active variable of same type
            existing_var = ClientEnvironmentVariable.objects.filter(
                client=client,
                variable_type=data['variable_type'],
                custom_name=data.get('custom_name', ''),
                is_active=True
            ).first()

            if existing_var:
                return Response({
                    'error': 'Variable already exists',
                    'message': f"An active variable of type '{data['variable_type']}' already exists. Delete the existing one first or update it.",
                    'timestamp': timezone.now()
                }, status=status.HTTP_409_CONFLICT)

            # Create new variable
            variable = ClientEnvironmentVariable(
                client=client,
                variable_type=data['variable_type'],
                custom_name=data.get('custom_name', ''),
                description=data.get('description', ''),
                is_active=True
            )

            # Set encrypted value
            variable.set_encrypted_value(data['variable_value'])
            variable.save()

            # Send notification
            try:
                notify_credentials_updated(client, f"Environment Variable ({data['variable_type']})")
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")

            logger.info(f"Environment variable created for client {client.name}: {variable.id}")

            return Response({
                'success': True,
                'message': 'Environment variable created successfully',
                'data': {
                    'id': str(variable.id),
                    'variable_type': variable.variable_type,
                    'custom_name': variable.custom_name,
                    'description': variable.description,
                    'is_active': variable.is_active,
                    'created_at': variable.created_at,
                    'updated_at': variable.updated_at
                },
                'timestamp': timezone.now()
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating environment variable: {e}")
            return Response({
                'error': 'Creation failed',
                'message': 'Failed to create environment variable',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request: Request, variable_id: str) -> Response:
        """
        Update an environment variable.
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            # Get the variable
            variable = get_object_or_404(
                ClientEnvironmentVariable,
                id=variable_id,
                client=client
            )

            data = request.data

            # Update fields
            if 'description' in data:
                variable.description = data['description']

            if 'custom_name' in data:
                variable.custom_name = data['custom_name']

            if 'variable_value' in data:
                variable.set_encrypted_value(data['variable_value'])

            if 'is_active' in data:
                variable.is_active = bool(data['is_active'])

            variable.save()

            # Send notification
            try:
                notify_credentials_updated(client, f"Environment Variable ({variable.variable_type})")
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")

            logger.info(f"Environment variable updated for client {client.name}: {variable.id}")

            return Response({
                'success': True,
                'message': 'Environment variable updated successfully',
                'data': {
                    'id': str(variable.id),
                    'variable_type': variable.variable_type,
                    'custom_name': variable.custom_name,
                    'description': variable.description,
                    'is_active': variable.is_active,
                    'created_at': variable.created_at,
                    'updated_at': variable.updated_at
                },
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating environment variable: {e}")
            return Response({
                'error': 'Update failed',
                'message': 'Failed to update environment variable',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request: Request, variable_id: str) -> Response:
        """
        Delete an environment variable.
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            # Get the variable
            variable = get_object_or_404(
                ClientEnvironmentVariable,
                id=variable_id,
                client=client
            )

            variable_type = variable.variable_type
            variable.delete()

            # Send notification
            try:
                send_notification(
                    client=client,
                    notification_type='ENVIRONMENT_VARIABLE_UPDATED',
                    title='Environment Variable Deleted',
                    message=f'Environment variable of type "{variable_type}" has been deleted.',
                    metadata={'variable_type': variable_type, 'action': 'deleted'}
                )
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")

            logger.info(f"Environment variable deleted for client {client.name}: {variable_id}")

            return Response({
                'success': True,
                'message': 'Environment variable deleted successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error deleting environment variable: {e}")
            return Response({
                'error': 'Deletion failed',
                'message': 'Failed to delete environment variable',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationView(APIView):
    """
    Manage client notifications.

    GET /api/v1/core/notifications/
    PUT /api/v1/core/notifications/<notification_id>/read/
    DELETE /api/v1/core/notifications/<notification_id>/
    """
    permission_classes = [IsValidClient]

    def get(self, request: Request, notification_id: str = None) -> Response:
        """
        Get notifications for the authenticated client.
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            if notification_id:
                # Get specific notification
                notification = get_object_or_404(
                    Notification,
                    id=notification_id,
                    client=client
                )

                return Response({
                    'success': True,
                    'data': {
                        'id': str(notification.id),
                        'notification_type': notification.notification_type,
                        'title': notification.title,
                        'message': notification.message,
                        'status': notification.status,
                        'channels_sent': notification.channels_sent,
                        'reference_id': notification.reference_id,
                        'metadata': notification.metadata,
                        'is_read': notification.is_read,
                        'read_at': notification.read_at,
                        'created_at': notification.created_at,
                        'email_sent': notification.email_sent,
                        'whatsapp_sent': notification.whatsapp_sent,
                        'error_message': notification.error_message
                    },
                    'timestamp': timezone.now()
                }, status=status.HTTP_200_OK)
            else:
                # Get all notifications for client
                notifications = Notification.objects.filter(
                    client=client
                ).order_by('-created_at')

                # Apply filters
                notification_type = request.query_params.get('type')
                if notification_type:
                    notifications = notifications.filter(notification_type=notification_type)

                is_read = request.query_params.get('read')
                if is_read is not None:
                    notifications = notifications.filter(is_read=is_read.lower() == 'true')

                status_filter = request.query_params.get('status')
                if status_filter:
                    notifications = notifications.filter(status=status_filter.upper())

                # Pagination
                page_size = min(int(request.query_params.get('page_size', 20)), 100)
                page = int(request.query_params.get('page', 1))
                start = (page - 1) * page_size
                end = start + page_size

                paginated_notifications = notifications[start:end]
                total_count = notifications.count()
                unread_count = Notification.objects.get_unread_count(client)

                notification_data = []
                for notification in paginated_notifications:
                    notification_data.append({
                        'id': str(notification.id),
                        'notification_type': notification.notification_type,
                        'title': notification.title,
                        'message': notification.message,
                        'status': notification.status,
                        'channels_sent': notification.channels_sent,
                        'reference_id': notification.reference_id,
                        'is_read': notification.is_read,
                        'read_at': notification.read_at,
                        'created_at': notification.created_at,
                        'email_sent': notification.email_sent,
                        'whatsapp_sent': notification.whatsapp_sent
                    })

                return Response({
                    'success': True,
                    'data': {
                        'notifications': notification_data,
                        'unread_count': unread_count,
                        'pagination': {
                            'page': page,
                            'page_size': page_size,
                            'total_count': total_count,
                            'total_pages': (total_count + page_size - 1) // page_size
                        }
                    },
                    'timestamp': timezone.now()
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return Response({
                'error': 'Query failed',
                'message': 'Failed to retrieve notifications',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request: Request, notification_id: str, action: str = None) -> Response:
        """
        Update notification (mark as read).
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            notification = get_object_or_404(
                Notification,
                id=notification_id,
                client=client
            )

            if action == 'read':
                notification.mark_as_read()
                message = 'Notification marked as read'
            else:
                return Response({
                    'error': 'Invalid action',
                    'message': 'Supported actions: read',
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                'success': True,
                'message': message,
                'data': {
                    'id': str(notification.id),
                    'is_read': notification.is_read,
                    'read_at': notification.read_at
                },
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating notification: {e}")
            return Response({
                'error': 'Update failed',
                'message': 'Failed to update notification',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request: Request, notification_id: str) -> Response:
        """
        Delete a notification.
        """
        try:
            client = request.user
            if not isinstance(client, Client):
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            notification = get_object_or_404(
                Notification,
                id=notification_id,
                client=client
            )

            notification.delete()

            return Response({
                'success': True,
                'message': 'Notification deleted successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            return Response({
                'error': 'Deletion failed',
                'message': 'Failed to delete notification',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
