"""
MPesa API v1 views for handling payment operations.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from mpesa.models import Transaction, CallbackLog, MpesaConfiguration
from mpesa.services.stk_push_service import STKPushService
from mpesa.services.callback_service import CallbackService
from mpesa.services.transaction_service import TransactionService
from core.utils.phone import normalize_phone_number, PhoneNumberError
from core.exceptions import MPesaException, ValidationException

from .serializers import (
    STKPushInitiateSerializer, STKPushResponseSerializer,
    PaymentStatusSerializer, MPesaCallbackSerializer,
    ManualValidationSerializer, TransactionListSerializer,
    ConnectionTestSerializer, BulkStatusCheckSerializer,
    ErrorResponseSerializer, SuccessResponseSerializer,
    HealthCheckSerializer
)

import logging
import uuid

logger = logging.getLogger(__name__)


class STKPushInitiateView(APIView):
    """
    Initiate STK Push payment request.

    POST /api/v1/mpesa/initiate/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Initiate STK Push payment."""
        try:
            # Validate request data
            serializer = STKPushInitiateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid request data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            client = request.user  # Client from authentication

            # Get client IP and user agent
            client_ip = self._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')

            # Initialize STK Push service
            stk_service = STKPushService()

            # Initiate payment
            result = stk_service.initiate_stk_push(
                client=client,
                phone_number=validated_data['phone_number'],
                amount=validated_data['amount'],
                description=validated_data['description'],
                reference=validated_data.get('reference'),
                account_reference=validated_data.get('account_reference'),
                ip_address=client_ip,
                user_agent=user_agent
            )

            # Serialize response
            response_serializer = STKPushResponseSerializer(result)

            logger.info(f"STK Push initiated for client {client.name}: {result.get('transaction_id')}")

            return Response({
                'success': True,
                'message': 'STK Push initiated successfully',
                'data': response_serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_201_CREATED)

        except ValidationException as e:
            logger.warning(f"Validation error in STK Push: {e}")
            return Response({
                'error': 'Validation error',
                'message': str(e),
                'timestamp': timezone.now()
            }, status=status.HTTP_400_BAD_REQUEST)

        except MPesaException as e:
            logger.error(f"MPesa error in STK Push: {e}")
            return Response({
                'error': 'Payment processing error',
                'message': 'Failed to initiate payment. Please try again.',
                'timestamp': timezone.now()
            }, status=status.HTTP_502_BAD_GATEWAY)

        except Exception as e:
            logger.error(f"Unexpected error in STK Push: {e}")
            return Response({
                'error': 'Internal server error',
                'message': 'An unexpected error occurred',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


@method_decorator(csrf_exempt, name='dispatch')
class MPesaCallbackView(APIView):
    """
    Handle MPesa callback notifications.

    POST /api/v1/mpesa/callback/
    """
    permission_classes = []  # No authentication for callbacks

    def post(self, request):
        """Process MPesa callback."""
        try:
            # Log the callback
            callback_log = CallbackLog.objects.create(
                callback_type='STK_PUSH',
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                headers=dict(request.META),
                raw_data=request.data
            )

            # Validate callback data
            serializer = MPesaCallbackSerializer(data=request.data)
            if not serializer.is_valid():
                callback_log.mark_as_processed(
                    success=False,
                    error_message=f"Invalid callback data: {serializer.errors}"
                )
                return Response({
                    'ResultCode': 1,
                    'ResultDesc': 'Invalid callback data'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Process callback
            callback_service = CallbackService()
            result = callback_service.process_stk_callback(
                request.data,
                callback_log
            )

            callback_log.mark_as_processed(success=True)

            logger.info(f"Processed MPesa callback: {result.get('transaction_id')}")

            return Response({
                'ResultCode': 0,
                'ResultDesc': 'Callback processed successfully'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing MPesa callback: {e}")
            if 'callback_log' in locals():
                callback_log.mark_as_processed(
                    success=False,
                    error_message=str(e)
                )

            return Response({
                'ResultCode': 1,
                'ResultDesc': 'Callback processing failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class PaymentStatusView(APIView):
    """
    Check payment status by transaction ID.

    GET /api/v1/mpesa/status/<transaction_id>/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, transaction_id):
        """Get payment status."""
        try:
            client = request.user

            # Get transaction
            transaction = get_object_or_404(
                Transaction,
                transaction_id=transaction_id,
                client=client
            )

            # Serialize transaction data
            serializer = PaymentStatusSerializer(transaction)

            return Response({
                'success': True,
                'data': serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error getting payment status: {e}")
            return Response({
                'error': 'Status check failed',
                'message': 'Failed to retrieve payment status',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManualValidationView(APIView):
    """
    Manually validate offline payments (Paybill/Till).

    POST /api/v1/mpesa/validate/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Validate manual payment."""
        try:
            # Validate request data
            serializer = ManualValidationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid request data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            validated_data = serializer.validated_data
            client = request.user

            # Check for duplicate receipt numbers
            existing_transaction = Transaction.objects.filter(
                client=client,
                mpesa_receipt_number=validated_data['mpesa_receipt_number']
            ).first()

            if existing_transaction:
                return Response({
                    'error': 'Duplicate transaction',
                    'message': 'Transaction with this receipt number already exists',
                    'timestamp': timezone.now()
                }, status=status.HTTP_409_CONFLICT)

            # Create transaction record
            transaction = Transaction.objects.create(
                client=client,
                transaction_type=f"C2B_{validated_data['transaction_type']}",
                phone_number=validated_data['phone_number'],
                amount=validated_data['amount'],
                description=validated_data['description'],
                reference=validated_data.get('account_reference', ''),
                mpesa_receipt_number=validated_data['mpesa_receipt_number'],
                transaction_date=validated_data['transaction_date'],
                status='SUCCESSFUL',
                response_code='0',
                response_description='Manual validation successful',
                callback_received=True,
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            # Serialize response
            serializer = PaymentStatusSerializer(transaction)

            logger.info(f"Manual payment validated for client {client.name}: {transaction.transaction_id}")

            return Response({
                'success': True,
                'message': 'Payment validated successfully',
                'data': serializer.data,
                'timestamp': timezone.now()
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error in manual validation: {e}")
            return Response({
                'error': 'Validation failed',
                'message': 'Failed to validate payment',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class TransactionListView(APIView):
    """
    List client transactions with filtering and pagination.

    GET /api/v1/mpesa/transactions/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionListSerializer

    def get(self, request):
        """Get transaction list."""
        try:
            client = request.user

            # Get query parameters
            status_filter = request.query_params.get('status')
            transaction_type = request.query_params.get('type')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            phone_number = request.query_params.get('phone_number')

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

            if phone_number:
                try:
                    normalized_phone = normalize_phone_number(phone_number)
                    queryset = queryset.filter(phone_number=normalized_phone)
                except PhoneNumberError:
                    pass  # Ignore invalid phone numbers

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
            logger.error(f"Error getting transaction list: {e}")
            return Response({
                'error': 'Query failed',
                'message': 'Failed to retrieve transactions',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BulkStatusCheckView(APIView):
    """
    Check status of multiple transactions.

    POST /api/v1/mpesa/bulk-status/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Check bulk transaction status."""
        try:
            # Validate request data
            serializer = BulkStatusCheckSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'message': 'Invalid request data',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            transaction_ids = serializer.validated_data['transaction_ids']
            client = request.user

            # Get transactions
            transactions = Transaction.objects.filter(
                transaction_id__in=transaction_ids,
                client=client
            )

            # Serialize data
            transaction_data = PaymentStatusSerializer(transactions, many=True).data

            # Create results map
            results = {str(t['transaction_id']): t for t in transaction_data}

            # Add missing transactions
            found_ids = set(results.keys())
            requested_ids = set(str(tid) for tid in transaction_ids)
            missing_ids = requested_ids - found_ids

            for missing_id in missing_ids:
                results[missing_id] = {
                    'transaction_id': missing_id,
                    'status': 'NOT_FOUND',
                    'error': 'Transaction not found'
                }

            return Response({
                'success': True,
                'data': {
                    'results': results,
                    'summary': {
                        'requested': len(transaction_ids),
                        'found': len(found_ids),
                        'missing': len(missing_ids)
                    }
                },
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in bulk status check: {e}")
            return Response({
                'error': 'Bulk check failed',
                'message': 'Failed to check transaction status',
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConnectionTestView(APIView):
    """
    Test connection to MPesa API.

    POST /api/v1/mpesa/test-connection/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Test MPesa connection."""
        try:
            serializer = ConnectionTestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    'error': 'Validation failed',
                    'details': serializer.errors,
                    'timestamp': timezone.now()
                }, status=status.HTTP_400_BAD_REQUEST)

            environment = serializer.validated_data.get('environment', 'sandbox')

            # Test connection
            from mpesa.mpesa_client import get_mpesa_client
            client = get_mpesa_client(environment)
            result = client.test_connection()

            return Response({
                'success': True,
                'data': result,
                'timestamp': timezone.now()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error testing MPesa connection: {e}")
            return Response({
                'error': 'Connection test failed',
                'message': str(e),
                'timestamp': timezone.now()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([])
def health_check(request):
    """
    Health check endpoint.

    GET /api/v1/health/
    """
    try:
        # Check database
        db_status = 'ok'
        try:
            Transaction.objects.count()
        except Exception:
            db_status = 'error'

        # Check cache
        cache_status = 'ok'
        try:
            cache.set('health_check', 'test', 10)
            cache.get('health_check')
        except Exception:
            cache_status = 'error'

        # Overall status
        overall_status = 'ok' if db_status == 'ok' and cache_status == 'ok' else 'error'

        return Response({
            'status': overall_status,
            'message': 'Service health check',
            'services': {
                'database': db_status,
                'cache': cache_status,
                'api': 'ok'
            },
            'timestamp': timezone.now()
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response({
            'status': 'error',
            'message': 'Health check failed',
            'timestamp': timezone.now()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
