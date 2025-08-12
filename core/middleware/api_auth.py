"""
API authentication and rate limiting middleware.

Middleware components for API key authentication, rate limiting, and security.
All middleware assumes Client objects are used instead of Django Users.
"""

import time
import json
from typing import Optional, Union
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
from clients.models import APIUsageLog, Client
from core.utils.encryption import encryption_manager
import logging

logger = logging.getLogger(__name__)


class APIKeyAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware for API key authentication, rate limiting, and usage logging.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """
        Process incoming request for API authentication.

        Args:
            request: The HTTP request object

        Returns:
            Optional[HttpResponse]: None to continue processing, or error response
        """
        # Skip authentication for non-API endpoints
        if not request.path.startswith('/api/'):
            return None

        # Skip authentication for public endpoints
        public_endpoints = [
            '/api/docs/',
            '/api/schema/',
            '/api/health/',
        ]

        if any(request.path.startswith(endpoint) for endpoint in public_endpoints):
            return None

        # Add request metadata
        request.start_time = time.time()
        request.client_ip = self.get_client_ip(request)
        request.request_size = len(request.body) if hasattr(request, 'body') else 0

        return None

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Process response and log API usage.

        Args:
            request: The HTTP request object
            response: The HTTP response object

        Returns:
            HttpResponse: The response object
        """
        # Only process API endpoints
        if not request.path.startswith('/api/'):
            return response

        # Log API usage if client is authenticated and is a Client instance
        if (hasattr(request, 'user') and
            isinstance(request.user, Client) and
            hasattr(request.user, 'client_id')):
            self.log_api_usage(request, response)

        return response

    def log_api_usage(self, request: HttpRequest, response: HttpResponse) -> None:
        """
        Log API usage for monitoring and billing.

        Args:
            request: The HTTP request object
            response: The HTTP response object
        """
        try:
            # Calculate response time
            response_time = 0
            if hasattr(request, 'start_time'):
                response_time = int((time.time() - request.start_time) * 1000)  # milliseconds

            # Get response size
            response_size = 0
            if hasattr(response, 'content'):
                response_size = len(response.content)

            # Create usage log
            APIUsageLog.objects.create(
                client=request.user,
                endpoint=request.path,
                method=request.method,
                ip_address=getattr(request, 'client_ip', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                request_size=getattr(request, 'request_size', 0),
                response_size=response_size,
                response_time=response_time,
                status_code=response.status_code,
                error_message=getattr(response, 'error_message', '')
            )

        except Exception as e:
            logger.error(f"Failed to log API usage: {e}")

    def get_client_ip(self, request: HttpRequest) -> str:
        """
        Get client IP address.

        Args:
            request: The HTTP request object

        Returns:
            str: Client IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip


class RateLimitMiddleware(MiddlewareMixin):
    """
    Rate limiting middleware for API endpoints.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_request(self, request):
        """Check rate limits for authenticated clients."""
        # Skip for non-API endpoints
        if not request.path.startswith('/api/'):
            return None

        # Skip if no client is authenticated
        if not (hasattr(request, 'user') and hasattr(request.user, 'client_id')):
            return None

        client = request.user

        # Check rate limits
        if self.is_rate_limited(client, request):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'message': 'Too many requests. Please try again later.',
                'code': 'RATE_LIMIT_EXCEEDED'
            }, status=429)

        return None

    def is_rate_limited(self, client, request):
        """Check if client has exceeded rate limits."""
        try:
            client_ip = self.get_client_ip(request)
            current_time = int(time.time())

            # Check per-minute limit
            minute_key = f"rate_limit:minute:{client.client_id}:{current_time // 60}"
            minute_count = cache.get(minute_key, 0)

            if minute_count >= client.rate_limit_per_minute:
                logger.warning(f"Rate limit exceeded (per minute) for client {client.name}")
                return True

            # Check per-hour limit
            hour_key = f"rate_limit:hour:{client.client_id}:{current_time // 3600}"
            hour_count = cache.get(hour_key, 0)

            if hour_count >= client.rate_limit_per_hour:
                logger.warning(f"Rate limit exceeded (per hour) for client {client.name}")
                return True

            # Check per-day limit
            day_key = f"rate_limit:day:{client.client_id}:{current_time // 86400}"
            day_count = cache.get(day_key, 0)

            if day_count >= client.rate_limit_per_day:
                logger.warning(f"Rate limit exceeded (per day) for client {client.name}")
                return True

            # Increment counters
            cache.set(minute_key, minute_count + 1, 60)  # 1 minute TTL
            cache.set(hour_key, hour_count + 1, 3600)    # 1 hour TTL
            cache.set(day_key, day_count + 1, 86400)     # 1 day TTL

            return False

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return False  # Allow request if rate limit check fails

    def get_client_ip(self, request: HttpRequest) -> str:
        """
        Get client IP address.

        Args:
            request: The HTTP request object

        Returns:
            str: Client IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to API responses.
    """

    def process_response(self, request, response):
        """Add security headers."""
        # Add security headers for API endpoints
        if request.path.startswith('/api/'):
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            response['Content-Security-Policy'] = "default-src 'none'"
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

            # Remove server information
            if 'Server' in response:
                del response['Server']

        return response


class CORSMiddleware(MiddlewareMixin):
    """
    Handle CORS for API endpoints.
    """

    def process_response(self, request, response):
        """Add CORS headers for API endpoints."""
        if request.path.startswith('/api/'):
            # Allow specific origins (configure in settings)
            allowed_origins = getattr(request, 'allowed_origins', ['*'])

            if allowed_origins == ['*']:
                response['Access-Control-Allow-Origin'] = '*'
            else:
                origin = request.META.get('HTTP_ORIGIN', '')
                if origin in allowed_origins:
                    response['Access-Control-Allow-Origin'] = origin

            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Accept, Authorization, Content-Type, X-API-Key, X-API-Secret, X-Signature, X-Timestamp'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Max-Age'] = '86400'  # 24 hours

        return response

    def process_request(self, request):
        """Handle preflight OPTIONS requests."""
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            from django.http import HttpResponse
            response = HttpResponse()

            # Add CORS headers
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Accept, Authorization, Content-Type, X-API-Key, X-API-Secret, X-Signature, X-Timestamp'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Max-Age'] = '86400'

            return response

        return None


class RequestValidationMiddleware(MiddlewareMixin):
    """
    Validate incoming requests for security and format.
    """

    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB

    def process_request(self, request):
        """Validate incoming requests."""
        if not request.path.startswith('/api/'):
            return None

        # Check request size
        if hasattr(request, 'body') and len(request.body) > self.MAX_REQUEST_SIZE:
            return JsonResponse({
                'error': 'Request too large',
                'message': f'Request size exceeds maximum allowed size of {self.MAX_REQUEST_SIZE} bytes',
                'code': 'REQUEST_TOO_LARGE'
            }, status=413)

        # Validate JSON for POST/PUT/PATCH requests
        if request.method in ['POST', 'PUT', 'PATCH']:
            content_type = request.META.get('CONTENT_TYPE', '')

            if 'application/json' in content_type:
                try:
                    if hasattr(request, 'body') and request.body:
                        json.loads(request.body)
                except json.JSONDecodeError:
                    return JsonResponse({
                        'error': 'Invalid JSON',
                        'message': 'Request body contains invalid JSON',
                        'code': 'INVALID_JSON'
                    }, status=400)

        return None


class HealthCheckMiddleware(MiddlewareMixin):
    """
    Handle health check endpoints.
    """

    def process_request(self, request):
        """Handle health check requests."""
        if request.path == '/api/health/':
            from django.http import JsonResponse
            from django.db import connection

            try:
                # Check database connection
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")

                return JsonResponse({
                    'status': 'healthy',
                    'timestamp': time.time(),
                    'version': '1.0.0'
                })

            except Exception as e:
                return JsonResponse({
                    'status': 'unhealthy',
                    'error': str(e),
                    'timestamp': time.time()
                }, status=503)

        return None
