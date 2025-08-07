"""
MPesa API client for handling authentication and API communication.
"""

import requests
import base64
import json
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from mpesa.models import MpesaCredentials, AccessToken
from core.exceptions import MPesaException, ConfigurationException
import logging

logger = logging.getLogger(__name__)


class MpesaClient:
    """
    Main MPesa API client for handling authentication and API requests.
    """

    def __init__(self, environment='sandbox'):
        """
        Initialize MPesa client.

        Args:
            environment (str): 'sandbox' or 'live'
        """
        self.environment = environment
        self.credentials = self._get_credentials()
        self.base_url = self.credentials.base_url if self.credentials else None
        self.timeout = getattr(settings, 'MPESA_CONFIG', {}).get('api_timeout_seconds', 30)

        if not self.credentials:
            raise ConfigurationException(
                f"No MPesa credentials found for environment: {environment}"
            )

    def _get_credentials(self):
        """Get MPesa credentials for the environment."""
        return MpesaCredentials.objects.get_active_credentials(self.environment)

    def get_access_token(self):
        """
        Get access token for MPesa API authentication.
        Uses caching to avoid frequent API calls.

        Returns:
            str: Access token
        """
        try:
            # Check cache first
            cache_key = f"mpesa_token:{self.environment}"
            cached_token = cache.get(cache_key)

            if cached_token:
                return cached_token

            # Check database cache
            try:
                token_obj = AccessToken.objects.get(environment=self.environment)
                if not token_obj.is_expired():
                    token = token_obj.get_token()
                    if token:
                        # Cache in Redis for faster access
                        cache.set(cache_key, token, 3300)  # 55 minutes
                        return token
            except AccessToken.DoesNotExist:
                pass

            # Get new token from API
            token = self._fetch_access_token()

            # Cache the token
            cache.set(cache_key, token, 3300)  # 55 minutes

            return token

        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            raise MPesaException(f"Failed to authenticate with MPesa: {e}")

    def _fetch_access_token(self):
        """Fetch new access token from MPesa API."""
        try:
            creds = self.credentials.get_decrypted_credentials()
            if not creds:
                raise ConfigurationException("Failed to decrypt MPesa credentials")

            # Create authorization header
            auth_string = f"{creds['consumer_key']}:{creds['consumer_secret']}"
            auth_bytes = auth_string.encode('ascii')
            auth_header = base64.b64encode(auth_bytes).decode('ascii')

            # Make request
            url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
            headers = {
                'Authorization': f'Basic {auth_header}',
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            access_token = data.get('access_token')
            expires_in = int(data.get('expires_in', 3599))

            if not access_token:
                raise MPesaException("No access token in response")

            # Store in database
            token_obj, created = AccessToken.objects.get_or_create(
                environment=self.environment,
                defaults={'access_token': '', 'expires_at': timezone.now()}
            )
            token_obj.set_token(access_token, expires_in)

            logger.info(f"Successfully obtained MPesa access token for {self.environment}")
            return access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error while fetching access token: {e}")
            raise MPesaException(f"Network error while authenticating: {e}")
        except Exception as e:
            logger.error(f"Error fetching access token: {e}")
            raise MPesaException(f"Failed to get access token: {e}")

    def make_request(self, endpoint, data, method='POST'):
        """
        Make authenticated request to MPesa API.

        Args:
            endpoint (str): API endpoint
            data (dict): Request data
            method (str): HTTP method

        Returns:
            dict: Response data
        """
        try:
            access_token = self.get_access_token()

            url = f"{self.base_url}{endpoint}"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            logger.info(f"Making {method} request to {endpoint}")
            logger.debug(f"Request data: {json.dumps(data, indent=2)}")

            if method.upper() == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
            elif method.upper() == 'GET':
                response = requests.get(url, params=data, headers=headers, timeout=self.timeout)
            else:
                raise MPesaException(f"Unsupported HTTP method: {method}")

            # Log response
            logger.info(f"MPesa API response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")

            # Handle response
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON response: {response.text}")
                raise MPesaException("Invalid response format from MPesa API")

            logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")

            # Check for HTTP errors
            if not response.ok:
                error_msg = response_data.get('errorMessage', f'HTTP {response.status_code}')
                raise MPesaException(f"MPesa API error: {error_msg}", details=response_data)

            return response_data

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for endpoint: {endpoint}")
            raise MPesaException("Request to MPesa API timed out")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error for endpoint: {endpoint}")
            raise MPesaException("Failed to connect to MPesa API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for endpoint {endpoint}: {e}")
            raise MPesaException(f"Network error: {e}")
        except MPesaException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in make_request: {e}")
            raise MPesaException(f"Unexpected error: {e}")

    def generate_password(self, timestamp=None):
        """
        Generate password for STK push requests.

        Args:
            timestamp (str): Timestamp in format YYYYMMDDHHMMSS

        Returns:
            tuple: (password, timestamp)
        """
        try:
            if not timestamp:
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

            creds = self.credentials.get_decrypted_credentials()
            if not creds:
                raise ConfigurationException("Failed to decrypt MPesa credentials")

            # Create password string
            password_str = f"{creds['business_shortcode']}{creds['passkey']}{timestamp}"

            # Encode to base64
            password_bytes = password_str.encode('ascii')
            password = base64.b64encode(password_bytes).decode('ascii')

            return password, timestamp

        except Exception as e:
            logger.error(f"Error generating password: {e}")
            raise MPesaException(f"Failed to generate password: {e}")

    def get_business_shortcode(self):
        """Get business shortcode from credentials."""
        if not self.credentials:
            raise ConfigurationException("No MPesa credentials available")
        return self.credentials.business_shortcode

    def validate_phone_number(self, phone_number):
        """
        Validate phone number for MPesa format.

        Args:
            phone_number (str): Phone number to validate

        Returns:
            str: Validated phone number in 254XXXXXXXXX format
        """
        from core.utils.phone import format_phone_for_mpesa

        try:
            return format_phone_for_mpesa(phone_number)
        except Exception as e:
            raise MPesaException(f"Invalid phone number: {e}")

    def test_connection(self):
        """
        Test connection to MPesa API.

        Returns:
            dict: Test results
        """
        try:
            # Try to get access token
            start_time = timezone.now()
            token = self.get_access_token()
            end_time = timezone.now()

            response_time = (end_time - start_time).total_seconds() * 1000  # milliseconds

            return {
                'status': 'success',
                'message': 'Successfully connected to MPesa API',
                'environment': self.environment,
                'response_time_ms': response_time,
                'base_url': self.base_url,
                'timestamp': timezone.now().isoformat()
            }

        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Failed to connect to MPesa API: {e}',
                'environment': self.environment,
                'base_url': self.base_url,
                'timestamp': timezone.now().isoformat()
            }

    def get_account_balance(self):
        """
        Get account balance from MPesa.

        Returns:
            dict: Account balance information
        """
        try:
            creds = self.credentials.get_decrypted_credentials()
            if not creds:
                raise ConfigurationException("Failed to decrypt MPesa credentials")

            # Generate password
            password, timestamp = self.generate_password()

            data = {
                "Initiator": creds['initiator_name'],
                "SecurityCredential": creds['security_credential'],
                "CommandID": "AccountBalance",
                "PartyA": creds['business_shortcode'],
                "IdentifierType": "4",
                "Remarks": "Account balance inquiry",
                "QueueTimeOutURL": f"{settings.MPESA_CONFIG.get('base_callback_url', '')}/timeout/",
                "ResultURL": f"{settings.MPESA_CONFIG.get('base_callback_url', '')}/balance/"
            }

            response = self.make_request('/mpesa/accountbalance/v1/query', data)
            return response

        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            raise MPesaException(f"Failed to get account balance: {e}")


# Singleton instances for different environments
_sandbox_client = None
_live_client = None


def get_mpesa_client(environment='sandbox'):
    """
    Get MPesa client instance (singleton pattern).

    Args:
        environment (str): 'sandbox' or 'live'

    Returns:
        MpesaClient: MPesa client instance
    """
    global _sandbox_client, _live_client

    if environment == 'sandbox':
        if _sandbox_client is None:
            _sandbox_client = MpesaClient('sandbox')
        return _sandbox_client
    elif environment == 'live':
        if _live_client is None:
            _live_client = MpesaClient('live')
        return _live_client
    else:
        raise ValueError(f"Invalid environment: {environment}")


def clear_client_cache():
    """Clear cached client instances (useful for testing)."""
    global _sandbox_client, _live_client
    _sandbox_client = None
    _live_client = None
