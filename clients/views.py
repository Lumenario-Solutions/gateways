"""
Client management views for API client operations.

All views use API key authentication and work with Client objects.
"""

from typing import Dict, Any, Optional
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from django.core.cache import cache
from datetime import datetime, timedelta

# Import our custom permissions
from clients.permissions.api_client_permissions import IsValidClient, ClientOwnerPermission

from clients.models import Client, ClientConfiguration, ClientAPIKey, APIUsageLog
from mpesa.models import Transaction
from core.exceptions import ValidationException
from core.utils.encryption import encryption_manager

from .serializers.client_serializer import (
    ClientRegistrationSerializer, ClientRegistrationResponseSerializer,
    ClientResponseSerializer, ClientUpdateSerializer, APIKeyGenerationSerializer,
    APIKeyResponseSerializer, APIKeyListSerializer, ClientConfigurationSerializer,
    IPWhitelistSerializer, UsageStatsSerializer, ClientStatsSerializer,
    WebhookTestSerializer, WebhookTestResponseSerializer,
    ClientSearchSerializer, BulkClientActionSerializer
)

import logging
import uuid

logger = logging.getLogger(__name__)


class ClientRegistrationView(APIView):
    """
    Register a new API client.

    POST /api/v1/clients/register/
    """
    permission_classes = []  # Public endpoint for registration

    def post(self, request):
        """Register a new client."""
        try:
            # Validate request data
            serializer = ClientRegistrationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid registration data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            # Create client with API credentials
            client, api_secret = Client.objects.create_client(
                name=validated_data['name'],
                email=validated_data['email'],
                description=validated_data.get('description', ''),
                plan=validated_data.get('plan', 'free'),
                webhook_url=validated_data.get('webhook_url')
            )

            # Create default configuration
            ClientConfiguration.objects.create(client=client)

            # Prepare response
            response_data = {
                'client': ClientResponseSerializer(client).data,
                'api_secret': api_secret,
                'message': 'Client registered successfully. Store the API secret securely - it will not be shown again.'
            }

            response_serializer = ClientRegistrationResponseSerializer(response_data)

            logger.info(f"New client registered: {client.name} ({client.client_id})")

            return Response({
                'success': True,
                'data': response_serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error registering client: {e}")
            return Response({
                'error': 'Registration failed',
                'message': 'Failed to register client',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientProfileView(APIView):
    """
    Get or update client profile.

    GET /api/v1/clients/profile/
    PUT /api/v1/clients/profile/
    """
    permission_classes = [IsValidClient]

    def get(self, request: Request) -> Response:
        """
        Get client profile.

        Args:
            request: The HTTP request object

        Returns:
            Response: JSON response with client profile data
        """
        try:
            # Explicit client validation and type checking
            client = request.user
            if not isinstance(client, Client):
                logger.error(f"Invalid user type in profile request: {type(client)}")
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            serializer = ClientResponseSerializer(client)

            return Response({
                'success': True,
                'data': serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting client profile: {e}")
            return Response({
                'error': 'Profile retrieval failed',
                'message': 'Failed to retrieve client profile',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request: Request) -> Response:
        """
        Update client profile.

        Args:
            request: The HTTP request containing profile updates

        Returns:
            Response: JSON response with updated profile data
        """
        try:
            # Explicit client validation and type checking
            client = request.user
            if not isinstance(client, Client):
                logger.error(f"Invalid user type in profile update request: {type(client)}")
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            # Validate update data
            serializer = ClientUpdateSerializer(client, data=request.data, partial=True)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid update data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            # Update client
            updated_client = serializer.save()

            # Return updated profile
            response_serializer = ClientResponseSerializer(updated_client)

            logger.info(f"Client profile updated: {client.name}")

            return Response({
                'success': True,
                'data': response_serializer.data,
                'message': 'Profile updated successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating client profile: {e}")
            return Response({
                'error': 'Update failed',
                'message': 'Failed to update client profile',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class APIKeyManagementView(APIView):
    """
    Manage API keys for a client.

    GET /api/v1/clients/api-keys/
    POST /api/v1/clients/api-keys/
    """
    permission_classes = [IsValidClient]

    def get(self, request: Request) -> Response:
        """
        List client's API keys.

        Args:
            request: The HTTP request object

        Returns:
            Response: JSON response with list of API keys
        """
        try:
            # Explicit client validation and type checking
            client = request.user
            if not isinstance(client, Client):
                logger.error(f"Invalid user type in API keys list request: {type(client)}")
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            api_keys = ClientAPIKey.objects.filter(client=client).order_by('-created_at')

            serializer = APIKeyListSerializer(api_keys, many=True)

            return Response({
                'success': True,
                'data': {
                    'api_keys': serializer.data,
                    'count': api_keys.count()
                },
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error listing API keys: {e}")
            return Response({
                'error': 'Listing failed',
                'message': 'Failed to retrieve API keys',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request: Request) -> Response:
        """
        Generate new API key.

        Args:
            request: The HTTP request containing API key generation parameters

        Returns:
            Response: JSON response with new API key details
        """
        try:
            # Explicit client validation and type checking
            client = request.user
            if not isinstance(client, Client):
                logger.error(f"Invalid user type in API key generation request: {type(client)}")
                return Response({
                    'error': 'Authentication error',
                    'message': 'Invalid client authentication',
                    'timestamp': timezone.now()
                }, status=status.HTTP_401_UNAUTHORIZED)

            # Validate request data
            serializer = APIKeyGenerationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid API key data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            # Check for duplicate names
            if ClientAPIKey.objects.filter(
                client=client,
                name=validated_data['name'],
                environment=validated_data['environment']
            ).exists():
                return Response({
                    'error': 'Duplicate name',
                    'message': 'API key with this name already exists for this environment',
                    'timestamp': timezone.now()
                }, status=status.HTTP_409_CONFLICT)

            # Generate API key and secret
            api_key = encryption_manager.generate_api_key(32)
            api_secret = encryption_manager.generate_api_key(64)

            # Create API key record
            client_api_key = ClientAPIKey.objects.create(
                client=client,
                name=validated_data['name'],
                environment=validated_data['environment'],
                api_key=api_key,
                api_secret_hash=encryption_manager.hash_data(api_secret),
                permissions=validated_data.get('permissions', []),
                expires_at=validated_data.get('expires_at')
            )

            # Prepare response
            response_data = {
                'api_key': api_key,
                'api_secret': api_secret,
                'name': client_api_key.name,
                'environment': client_api_key.environment,
                'created_at': client_api_key.created_at,
                'expires_at': client_api_key.expires_at
            }

            response_serializer = APIKeyResponseSerializer(response_data)

            logger.info(f"New API key generated for client {client.name}: {client_api_key.name}")

            return Response({
                'success': True,
                'data': response_serializer.data,
                'message': 'API key generated successfully. Store the secret securely - it will not be shown again.',
                'timestamp': timezone.now()
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error generating API key: {e}")
            return Response({
                'error': 'Generation failed',
                'message': 'Failed to generate API key',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class APIKeyDetailView(APIView):
    """
    Manage specific API key.

    DELETE /api/v1/clients/api-keys/<api_key>/
    PUT /api/v1/clients/api-keys/<api_key>/
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, api_key):
        """Deactivate API key."""
        try:
            client = request.user

            client_api_key = get_object_or_404(
                ClientAPIKey,
                api_key=api_key,
                client=client
            )

            # Deactivate instead of deleting for audit trail
            client_api_key.is_active = False
            client_api_key.save()

            logger.info(f"API key deactivated for client {client.name}: {client_api_key.name}")

            return Response({
                'success': True,
                'message': 'API key deactivated successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error deactivating API key: {e}")
            return Response({
                'error': 'Deactivation failed',
                'message': 'Failed to deactivate API key',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, api_key):
        """Update API key settings."""
        try:
            client = request.user

            client_api_key = get_object_or_404(
                ClientAPIKey,
                api_key=api_key,
                client=client
            )

            # Update allowed fields
            if 'name' in request.data:
                client_api_key.name = request.data['name']

            if 'permissions' in request.data:
                client_api_key.permissions = request.data['permissions']

            if 'is_active' in request.data:
                client_api_key.is_active = request.data['is_active']

            client_api_key.save()

            serializer = APIKeyListSerializer(client_api_key)

            return Response({
                'success': True,
                'data': serializer.data,
                'message': 'API key updated successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating API key: {e}")
            return Response({
                'error': 'Update failed',
                'message': 'Failed to update API key',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientConfigurationView(APIView):
    """
    Get or update client configuration.

    GET /api/v1/clients/configuration/
    PUT /api/v1/clients/configuration/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get client configuration."""
        try:
            client = request.user

            # Get or create configuration
            config, created = ClientConfiguration.objects.get_or_create(client=client)

            serializer = ClientConfigurationSerializer(config)

            return Response({
                'success': True,
                'data': serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting client configuration: {e}")
            return Response({
                'error': 'Configuration retrieval failed',
                'message': 'Failed to retrieve configuration',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        """Update client configuration."""
        try:
            client = request.user

            # Get or create configuration
            config, created = ClientConfiguration.objects.get_or_create(client=client)

            # Validate update data
            serializer = ClientConfigurationSerializer(config, data=request.data, partial=True)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid configuration data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            # Update configuration
            updated_config = serializer.save()

            logger.info(f"Client configuration updated: {client.name}")

            return Response({
                'success': True,
                'data': ClientConfigurationSerializer(updated_config).data,
                'message': 'Configuration updated successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating client configuration: {e}")
            return Response({
                'error': 'Update failed',
                'message': 'Failed to update configuration',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClientStatsView(APIView):
    """
    Get client statistics and analytics.

    GET /api/v1/clients/stats/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get client statistics."""
        try:
            client = request.user

            # Get date range from query params
            days = int(request.query_params.get('days', 30))
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)

            # Transaction statistics
            transaction_stats = self._get_transaction_stats(client, start_date, end_date)

            # Usage statistics
            usage_stats = self._get_usage_stats(client, start_date, end_date)

            # API keys count
            api_keys_count = ClientAPIKey.objects.filter(client=client, is_active=True).count()

            # Last activity
            last_activity = max(
                client.last_api_call or client.created_at,
                Transaction.objects.filter(client=client).aggregate(
                    last_transaction=models.Max('created_at')
                )['last_transaction'] or client.created_at
            )

            stats_data = {
                'client_info': ClientResponseSerializer(client).data,
                'transaction_stats': transaction_stats,
                'usage_stats': usage_stats,
                'api_keys_count': api_keys_count,
                'last_activity': last_activity
            }

            return Response({
                'success': True,
                'data': stats_data,
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting client stats: {e}")
            return Response({
                'error': 'Stats retrieval failed',
                'message': 'Failed to retrieve statistics',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_transaction_stats(self, client, start_date, end_date):
        """Get transaction statistics for client."""
        transactions = Transaction.objects.filter(
            client=client,
            created_at__gte=start_date,
            created_at__lte=end_date
        )

        total_count = transactions.count()
        successful_count = transactions.filter(status='SUCCESSFUL').count()
        failed_count = transactions.filter(status='FAILED').count()
        pending_count = transactions.filter(status__in=['PENDING', 'PROCESSING']).count()

        total_amount = transactions.filter(status='SUCCESSFUL').aggregate(
            total=Sum('amount')
        )['total'] or 0

        return {
            'total_transactions': total_count,
            'successful_transactions': successful_count,
            'failed_transactions': failed_count,
            'pending_transactions': pending_count,
            'total_amount': float(total_amount),
            'success_rate': (successful_count / total_count * 100) if total_count > 0 else 0
        }

    def _get_usage_stats(self, client, start_date, end_date):
        """Get API usage statistics for client."""
        usage_logs = APIUsageLog.objects.filter(
            client=client,
            timestamp__gte=start_date,
            timestamp__lte=end_date
        )

        total_requests = usage_logs.count()
        successful_requests = usage_logs.filter(status_code__lt=400).count()
        failed_requests = total_requests - successful_requests

        avg_response_time = usage_logs.aggregate(
            avg_time=Avg('response_time')
        )['avg_time'] or 0

        total_data = usage_logs.aggregate(
            total_request=Sum('request_size'),
            total_response=Sum('response_size')
        )

        total_data_transferred = (total_data['total_request'] or 0) + (total_data['total_response'] or 0)

        return {
            'period_start': start_date,
            'period_end': end_date,
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'average_response_time': float(avg_response_time),
            'total_data_transferred': total_data_transferred
        }


class IPWhitelistView(APIView):
    """
    Manage IP whitelist for client.

    GET /api/v1/clients/ip-whitelist/
    PUT /api/v1/clients/ip-whitelist/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current IP whitelist."""
        try:
            client = request.user
            ip_addresses = client.get_allowed_ips_list()

            return Response({
                'success': True,
                'data': {
                    'ip_addresses': ip_addresses,
                    'count': len(ip_addresses)
                },
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting IP whitelist: {e}")
            return Response({
                'error': 'Retrieval failed',
                'message': 'Failed to retrieve IP whitelist',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        """Update IP whitelist."""
        try:
            client = request.user

            # Validate request data
            serializer = IPWhitelistSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid IP addresses',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            ip_addresses = serializer.validated_data['ip_addresses']

            # Update client's allowed IPs
            client.allowed_ips = ','.join(ip_addresses)
            client.save(update_fields=['allowed_ips'])

            logger.info(f"IP whitelist updated for client {client.name}: {len(ip_addresses)} IPs")

            return Response({
                'success': True,
                'data': {
                    'ip_addresses': ip_addresses,
                    'count': len(ip_addresses)
                },
                'message': 'IP whitelist updated successfully',
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error updating IP whitelist: {e}")
            return Response({
                'error': 'Update failed',
                'message': 'Failed to update IP whitelist',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WebhookTestView(APIView):
    """
    Test webhook endpoint.

    POST /api/v1/clients/test-webhook/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Test webhook endpoint."""
        try:
            # Validate request data
            serializer = WebhookTestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid webhook test data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data

            # Test webhook
            result = self._test_webhook(
                webhook_url=validated_data['webhook_url'],
                event_type=validated_data['event_type'],
                test_data=validated_data.get('test_data', {})
            )

            response_serializer = WebhookTestResponseSerializer(result)

            return Response({
                'success': True,
                'data': response_serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error testing webhook: {e}")
            return Response({
                'error': 'Test failed',
                'message': 'Failed to test webhook',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _test_webhook(self, webhook_url, event_type, test_data):
        """Test webhook endpoint with sample data."""
        import requests
        import time

        try:
            # Prepare test payload
            payload = {
                'event': event_type,
                'test': True,
                'transaction_id': str(uuid.uuid4()),
                'timestamp': timezone.now().isoformat(),
                **test_data
            }

            # Send request
            start_time = time.time()
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response_time = (time.time() - start_time) * 1000  # milliseconds

            return {
                'success': response.ok,
                'status_code': response.status_code,
                'response_time_ms': response_time,
                'response_headers': dict(response.headers),
                'response_body': response.text[:1000],  # Limit response body size
                'error_message': None if response.ok else f"HTTP {response.status_code}"
            }

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'status_code': 0,
                'response_time_ms': 30000,
                'response_headers': {},
                'response_body': '',
                'error_message': 'Request timeout (30 seconds)'
            }
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'status_code': 0,
                'response_time_ms': 0,
                'response_headers': {},
                'response_body': '',
                'error_message': 'Connection error'
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': 0,
                'response_time_ms': 0,
                'response_headers': {},
                'response_body': '',
                'error_message': str(e)
            }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_transactions(request):
    """
    Get client transactions.

    GET /api/v1/clients/transactions/
    """
    try:
        client = request.user

        # Import here to avoid circular imports
        from mpesa.api.v1.serializers import TransactionListSerializer

        # Get query parameters
        status_filter = request.query_params.get('status')
        transaction_type = request.query_params.get('type')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # Build query
        queryset = Transaction.objects.filter(client=client)

        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type.upper())

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)

        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # Order by creation date (newest first)
        queryset = queryset.order_by('-created_at')

        # Pagination
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        page = int(request.query_params.get('page', 1))
        start = (page - 1) * page_size
        end = start + page_size

        transactions = queryset[start:end]
        total_count = queryset.count()

        # Serialize data
        serializer = TransactionListSerializer(transactions, many=True)

        return Response({
            'success': True,
            'data': {
                'transactions': serializer.data,
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
        logger.error(f"Error getting client transactions: {e}")
        return Response({
            'error': 'Query failed',
            'message': 'Failed to retrieve transactions',
            'timestamp': timezone.now()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
