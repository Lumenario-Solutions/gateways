"""
Custom exception handlers for the payment gateway API.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides consistent error responses.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Get request info for logging
    request = context.get('request')
    view = context.get('view')

    if response is not None:
        # Customize the error response format
        custom_response_data = {
            'error': True,
            'message': 'An error occurred',
            'code': 'UNKNOWN_ERROR',
            'details': None,
            'timestamp': None
        }

        # Get error details based on exception type
        if hasattr(exc, 'detail'):
            if isinstance(exc.detail, dict):
                # Field-specific errors
                custom_response_data['details'] = exc.detail
                custom_response_data['message'] = 'Validation error'
                custom_response_data['code'] = 'VALIDATION_ERROR'
            elif isinstance(exc.detail, list):
                # Multiple errors
                custom_response_data['details'] = exc.detail
                custom_response_data['message'] = str(exc.detail[0]) if exc.detail else 'Error occurred'
                custom_response_data['code'] = 'VALIDATION_ERROR'
            else:
                # Single error message
                custom_response_data['message'] = str(exc.detail)
                custom_response_data['code'] = get_error_code_from_exception(exc)
        else:
            custom_response_data['message'] = str(exc)
            custom_response_data['code'] = get_error_code_from_exception(exc)

        # Add timestamp
        custom_response_data['timestamp'] = timezone.now().isoformat()

        # Log the error
        log_error(exc, request, view, response.status_code)

        response.data = custom_response_data

    else:
        # Handle exceptions not caught by DRF
        if isinstance(exc, Http404):
            response_data = {
                'error': True,
                'message': 'Resource not found',
                'code': 'NOT_FOUND',
                'details': None,
                'timestamp': timezone.now().isoformat()
            }
            response = Response(response_data, status=status.HTTP_404_NOT_FOUND)

        elif isinstance(exc, PermissionDenied):
            response_data = {
                'error': True,
                'message': 'Permission denied',
                'code': 'PERMISSION_DENIED',
                'details': None,
                'timestamp': timezone.now().isoformat()
            }
            response = Response(response_data, status=status.HTTP_403_FORBIDDEN)

        elif isinstance(exc, ValidationError):
            response_data = {
                'error': True,
                'message': 'Validation error',
                'code': 'VALIDATION_ERROR',
                'details': exc.message_dict if hasattr(exc, 'message_dict') else str(exc),
                'timestamp': timezone.now().isoformat()
            }
            response = Response(response_data, status=status.HTTP_400_BAD_REQUEST)

        else:
            # Generic server error
            response_data = {
                'error': True,
                'message': 'Internal server error',
                'code': 'INTERNAL_ERROR',
                'details': None,
                'timestamp': timezone.now().isoformat()
            }
            response = Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Log the error
        log_error(exc, request, view, response.status_code)

    return response


def get_error_code_from_exception(exc):
    """
    Get appropriate error code based on exception type.
    """
    exception_type = type(exc).__name__

    error_code_mapping = {
        'AuthenticationFailed': 'AUTHENTICATION_FAILED',
        'NotAuthenticated': 'NOT_AUTHENTICATED',
        'PermissionDenied': 'PERMISSION_DENIED',
        'NotFound': 'NOT_FOUND',
        'ValidationError': 'VALIDATION_ERROR',
        'ParseError': 'PARSE_ERROR',
        'MethodNotAllowed': 'METHOD_NOT_ALLOWED',
        'NotAcceptable': 'NOT_ACCEPTABLE',
        'UnsupportedMediaType': 'UNSUPPORTED_MEDIA_TYPE',
        'Throttled': 'RATE_LIMITED',
        'APIException': 'API_ERROR',
    }

    return error_code_mapping.get(exception_type, 'UNKNOWN_ERROR')


def log_error(exc, request, view, status_code):
    """
    Log error details for monitoring and debugging.
    """
    try:
        # Prepare log data
        log_data = {
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
            'status_code': status_code,
            'request_method': getattr(request, 'method', None),
            'request_path': getattr(request, 'path', None),
            'view_name': getattr(view, '__class__', {}).get('__name__', 'Unknown'),
            'user_agent': getattr(request, 'META', {}).get('HTTP_USER_AGENT', ''),
            'client_ip': get_client_ip(request) if request else None,
        }

        # Add client info if available
        if hasattr(request, 'user') and hasattr(request.user, 'client_id'):
            log_data['client_id'] = str(request.user.client_id)
            log_data['client_name'] = request.user.name

        # Log based on severity
        if status_code >= 500:
            logger.error(f"Server Error: {log_data}")
        elif status_code >= 400:
            logger.warning(f"Client Error: {log_data}")
        else:
            logger.info(f"Error Response: {log_data}")

    except Exception as log_exc:
        logger.error(f"Failed to log error: {log_exc}")


def get_client_ip(request):
    """Get client IP address from request."""
    if not request:
        return None

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class PaymentGatewayException(Exception):
    """Base exception for payment gateway errors."""

    def __init__(self, message, code=None, details=None):
        self.message = message
        self.code = code or 'PAYMENT_GATEWAY_ERROR'
        self.details = details
        super().__init__(self.message)


class MPesaException(PaymentGatewayException):
    """Exception for MPesa-specific errors."""

    def __init__(self, message, code=None, details=None, mpesa_code=None):
        self.mpesa_code = mpesa_code
        super().__init__(message, code or 'MPESA_ERROR', details)


class AuthenticationException(PaymentGatewayException):
    """Exception for authentication errors."""

    def __init__(self, message, code=None, details=None):
        super().__init__(message, code or 'AUTHENTICATION_ERROR', details)


class RateLimitException(PaymentGatewayException):
    """Exception for rate limit errors."""

    def __init__(self, message, code=None, details=None):
        super().__init__(message, code or 'RATE_LIMIT_ERROR', details)


class ValidationException(PaymentGatewayException):
    """Exception for validation errors."""

    def __init__(self, message, code=None, details=None, field=None):
        self.field = field
        super().__init__(message, code or 'VALIDATION_ERROR', details)


class ConfigurationException(PaymentGatewayException):
    """Exception for configuration errors."""

    def __init__(self, message, code=None, details=None):
        super().__init__(message, code or 'CONFIGURATION_ERROR', details)


class TransactionException(PaymentGatewayException):
    """Exception for transaction processing errors."""

    def __init__(self, message, code=None, details=None, transaction_id=None):
        self.transaction_id = transaction_id
        super().__init__(message, code or 'TRANSACTION_ERROR', details)


def handle_mpesa_error(response_data, transaction=None):
    """
    Handle MPesa API error responses and raise appropriate exceptions.
    """
    if not response_data:
        raise MPesaException("Empty response from MPesa API")

    # Check for error codes
    error_code = response_data.get('errorCode')
    error_message = response_data.get('errorMessage', 'Unknown MPesa error')
    result_code = response_data.get('ResultCode')
    result_desc = response_data.get('ResultDesc', '')

    if error_code:
        raise MPesaException(
            message=error_message,
            code='MPESA_API_ERROR',
            mpesa_code=error_code,
            details={'error_code': error_code, 'error_message': error_message}
        )

    if result_code and result_code != '0':
        raise MPesaException(
            message=result_desc or f"MPesa error with code: {result_code}",
            code='MPESA_TRANSACTION_ERROR',
            mpesa_code=result_code,
            details={'result_code': result_code, 'result_desc': result_desc}
        )

    return response_data


def handle_phone_validation_error(phone_number):
    """Handle phone number validation errors."""
    raise ValidationException(
        message=f"Invalid phone number format: {phone_number}",
        code='INVALID_PHONE_NUMBER',
        field='phone_number',
        details={'phone_number': phone_number}
    )
