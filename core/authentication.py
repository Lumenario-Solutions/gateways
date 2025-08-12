"""
API Key authentication system for the payment gateway.

This module provides API key and signature-based authentication for clients,
completely replacing Django's session-based authentication for API access.
"""

from typing import Optional, Tuple, Union, Any
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from clients.models import Client, ClientAPIKey
import logging

logger = logging.getLogger(__name__)


class APIKeyAuthentication(BaseAuthentication):
    """
    API key authentication for clients.

    Expected header format:
    Authorization: ApiKey <api_key>:<api_secret>

    Or:
    X-API-Key: <api_key>
    X-API-Secret: <api_secret>
    """

    keyword = 'ApiKey'

    def authenticate(self, request: Request) -> Optional[Tuple[Client, None]]:
        """
        Authenticate the request and return a two-tuple of (client, token).

        Args:
            request: The HTTP request object

        Returns:
            Tuple[Client, None] or None: Client object and None (no token needed),
                                        or None if authentication not attempted
        """
        try:
            # Try Authorization header first
            auth_header = self.get_authorization_header(request)
            if auth_header:
                api_key, api_secret = self.parse_authorization_header(auth_header)
            else:
                # Try separate headers
                api_key = request.META.get('HTTP_X_API_KEY')
                api_secret = request.META.get('HTTP_X_API_SECRET')

            if not api_key or not api_secret:
                return None  # No authentication attempted

            # Authenticate the client
            client = self.authenticate_credentials(api_key, api_secret, request)

            # Log successful authentication
            logger.info(f"Client authenticated: {client.name} ({client.client_id})")

            # Update last API call
            client.update_last_api_call()

            return (client, None)  # Return client as user, no token needed

        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise AuthenticationFailed(_('Invalid authentication credentials.'))

    def get_authorization_header(self, request: Request) -> Optional[str]:
        """
        Get authorization header from request.

        Args:
            request: The HTTP request object

        Returns:
            Optional[str]: Authorization header value or None
        """
        auth = request.META.get('HTTP_AUTHORIZATION', '').strip()
        if auth.startswith(f'{self.keyword} '):
            return auth[len(self.keyword) + 1:]
        return None

    def parse_authorization_header(self, auth_header: str) -> Tuple[str, str]:
        """
        Parse API key and secret from authorization header.

        Args:
            auth_header: The authorization header value

        Returns:
            Tuple[str, str]: API key and secret

        Raises:
            AuthenticationFailed: If header format is invalid
        """
        try:
            api_key, api_secret = auth_header.split(':', 1)
            return api_key.strip(), api_secret.strip()
        except ValueError:
            raise AuthenticationFailed(_('Invalid authorization header format.'))

    def authenticate_credentials(self, api_key: str, api_secret: str, request: Request) -> Client:
        """
        Authenticate API key and secret.

        Args:
            api_key: The API key to validate
            api_secret: The API secret to validate
            request: The HTTP request object

        Returns:
            Client: The authenticated client

        Raises:
            AuthenticationFailed: If credentials are invalid
        """
        # Check cache first for performance
        cache_key = f"api_auth:{api_key}"
        cached_client = cache.get(cache_key)

        if cached_client:
            client = cached_client
        else:
            # Look up client by API key
            try:
                client = Client.objects.select_related('configuration').get(
                    api_key=api_key,
                    status='active'
                )
            except Client.DoesNotExist:
                # Also check ClientAPIKey model
                try:
                    client_api_key = ClientAPIKey.objects.select_related('client').get(
                        api_key=api_key,
                        is_active=True
                    )
                    if client_api_key.is_expired():
                        raise AuthenticationFailed(_('API key has expired.'))

                    # Verify secret for ClientAPIKey
                    if not client_api_key.verify_secret(api_secret):
                        raise AuthenticationFailed(_('Invalid API credentials.'))

                    client = client_api_key.client
                    client_api_key.update_last_used()

                except ClientAPIKey.DoesNotExist:
                    logger.warning(f"Authentication failed for API key: {api_key}")
                    raise AuthenticationFailed(_('Invalid API key.'))

            # Cache the client for 5 minutes
            cache.set(cache_key, client, 300)

        # Verify secret for main Client model
        if hasattr(client, 'verify_api_secret') and not client.verify_api_secret(api_secret):
            raise AuthenticationFailed(_('Invalid API credentials.'))

        # Check if client is active
        if not client.is_active():
            raise AuthenticationFailed(_('Client account is not active.'))

        # Check IP whitelist if configured
        client_ip = self.get_client_ip(request)
        if not client.is_ip_allowed(client_ip):
            logger.warning(f"IP not allowed for client {client.name}: {client_ip}")
            raise AuthenticationFailed(_('IP address not allowed.'))

        return client

    def get_client_ip(self, request: Request) -> str:
        """
        Get client IP address from request.

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

    def authenticate_header(self, request: Request) -> str:
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response.

        Args:
            request: The HTTP request object

        Returns:
            str: Authentication header value
        """
        return f'{self.keyword} realm="API"'


class SignatureAuthentication(BaseAuthentication):
    """
    HMAC signature-based authentication for enhanced security.

    Expected headers:
    X-API-Key: <api_key>
    X-Signature: <hmac_signature>
    X-Timestamp: <unix_timestamp>

    Signature is HMAC-SHA256 of: HTTP_METHOD + URI + TIMESTAMP + BODY
    """

    def authenticate(self, request: Request) -> Optional[Tuple[Client, None]]:
        """
        Authenticate using HMAC signature.

        Args:
            request: The HTTP request object

        Returns:
            Tuple[Client, None] or None: Client object and None, or None if not attempted
        """
        api_key = request.META.get('HTTP_X_API_KEY')
        signature = request.META.get('HTTP_X_SIGNATURE')
        timestamp = request.META.get('HTTP_X_TIMESTAMP')

        if not all([api_key, signature, timestamp]):
            return None  # No signature authentication attempted

        try:
            # Get client
            client = Client.objects.get(api_key=api_key, status='active')

            # Check timestamp (prevent replay attacks)
            import time
            current_timestamp = int(time.time())
            request_timestamp = int(timestamp)

            # Allow 5 minutes clock skew
            if abs(current_timestamp - request_timestamp) > 300:
                raise AuthenticationFailed(_('Request timestamp is too old or too new.'))

            # Verify signature
            if self.verify_signature(request, client, signature, timestamp):
                logger.info(f"Signature authentication successful for client: {client.name}")
                client.update_last_api_call()
                return (client, None)
            else:
                raise AuthenticationFailed(_('Invalid signature.'))

        except Client.DoesNotExist:
            raise AuthenticationFailed(_('Invalid API key.'))
        except ValueError:
            raise AuthenticationFailed(_('Invalid timestamp format.'))
        except Exception as e:
            logger.error(f"Signature authentication error: {e}")
            raise AuthenticationFailed(_('Authentication failed.'))

    def verify_signature(self, request: Request, client: Client, provided_signature: str, timestamp: str) -> bool:
        """
        Verify HMAC signature.

        Args:
            request: The HTTP request object
            client: The client making the request
            provided_signature: The signature provided in the request
            timestamp: The timestamp from the request

        Returns:
            bool: True if signature is valid
        """
        try:
            import hmac
            import hashlib

            # Get request body
            if hasattr(request, '_body'):
                body = request._body
            else:
                body = request.body

            if isinstance(body, bytes):
                body = body.decode('utf-8')

            # Create string to sign
            string_to_sign = f"{request.method}{request.get_full_path()}{timestamp}{body}"

            # Calculate signature
            secret = client.webhook_secret or client.api_secret_hash
            calculated_signature = hmac.new(
                secret.encode(),
                string_to_sign.encode(),
                hashlib.sha256
            ).hexdigest()

            # Compare signatures
            return hmac.compare_digest(provided_signature, calculated_signature)

        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

    def authenticate_header(self, request: Request) -> str:
        """
        Return authentication header for 401 responses.

        Args:
            request: The HTTP request object

        Returns:
            str: Authentication header value
        """
        return 'Signature realm="API"'


class MultiAuthentication(BaseAuthentication):
    """
    Combines multiple authentication methods.
    Tries API key authentication first, then signature authentication.
    """

    def __init__(self):
        self.api_key_auth = APIKeyAuthentication()
        self.signature_auth = SignatureAuthentication()

    def authenticate(self, request: Request) -> Optional[Tuple[Client, None]]:
        """
        Try multiple authentication methods.

        Args:
            request: The HTTP request object

        Returns:
            Tuple[Client, None] or None: Client object and None, or None if no auth succeeds
        """
        # Try API key authentication first
        result = self.api_key_auth.authenticate(request)
        if result:
            return result

        # Try signature authentication
        result = self.signature_auth.authenticate(request)
        if result:
            return result

        return None

    def authenticate_header(self, request: Request) -> str:
        """
        Return combined authentication header.

        Args:
            request: The HTTP request object

        Returns:
            str: Combined authentication header value
        """
        return f'{self.api_key_auth.authenticate_header(request)}, {self.signature_auth.authenticate_header(request)}'
