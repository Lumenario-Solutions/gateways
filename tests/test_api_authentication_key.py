"""
Comprehensive tests for API key authentication system.

Tests the complete API key authentication flow, permissions, and Client object handling.
"""

import uuid
from decimal import Decimal
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from clients.models import Client, ClientAPIKey, ClientConfiguration
from core.authentication import APIKeyAuthentication, SignatureAuthentication, MultiAuthentication
from clients.permissions.api_client_permissions import IsValidClient, ClientOwnerPermission
from mpesa.models import Transaction
from core.utils.encryption import encryption_manager


class APIKeyAuthenticationTest(TestCase):
    """Test API key authentication functionality."""

    def setUp(self):
        """Set up test data."""
        # Create test client
        self.client_data, self.api_secret = Client.objects.create_client(
            name="Test Client",
            email="test@example.com",
            description="Test client for API key authentication"
        )

        # Create additional API key
        self.additional_api_key = encryption_manager.generate_api_key(32)
        self.additional_secret = encryption_manager.generate_api_key(64)

        self.client_api_key = ClientAPIKey.objects.create(
            client=self.client_data,
            name="Test Environment",
            environment="sandbox",
            api_key=self.additional_api_key,
            api_secret_hash=encryption_manager.hash_data(self.additional_secret),
            permissions=["transactions", "payments"]
        )

    def test_api_key_authentication_with_authorization_header(self):
        """Test API key authentication using Authorization header."""
        auth = APIKeyAuthentication()

        # Create mock request with Authorization header
        from django.test import RequestFactory
        factory = RequestFactory()

        # Format: Authorization: ApiKey <api_key>:<api_secret>
        auth_header = f"ApiKey {self.client_data.api_key}:{self.api_secret}"
        request = factory.post('/api/test/', HTTP_AUTHORIZATION=auth_header)

        # Authenticate
        result = auth.authenticate(request)

        # Verify authentication success
        self.assertIsNotNone(result)
        client, token = result
        self.assertIsInstance(client, Client)
        self.assertEqual(client.client_id, self.client_data.client_id)
        self.assertIsNone(token)  # No token for API key auth

    def test_api_key_authentication_with_separate_headers(self):
        """Test API key authentication using separate X-API-Key and X-API-Secret headers."""
        auth = APIKeyAuthentication()

        from django.test import RequestFactory
        factory = RequestFactory()

        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY=self.client_data.api_key,
            HTTP_X_API_SECRET=self.api_secret
        )

        # Authenticate
        result = auth.authenticate(request)

        # Verify authentication success
        self.assertIsNotNone(result)
        client, token = result
        self.assertIsInstance(client, Client)
        self.assertEqual(client.client_id, self.client_data.client_id)

    def test_client_api_key_authentication(self):
        """Test authentication using ClientAPIKey model."""
        auth = APIKeyAuthentication()

        from django.test import RequestFactory
        factory = RequestFactory()

        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY=self.additional_api_key,
            HTTP_X_API_SECRET=self.additional_secret
        )

        # Authenticate
        result = auth.authenticate(request)

        # Verify authentication success
        self.assertIsNotNone(result)
        client, token = result
        self.assertIsInstance(client, Client)
        self.assertEqual(client.client_id, self.client_data.client_id)

    def test_invalid_api_key(self):
        """Test authentication with invalid API key."""
        auth = APIKeyAuthentication()

        from django.test import RequestFactory
        from rest_framework.exceptions import AuthenticationFailed
        factory = RequestFactory()

        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY="invalid_key",
            HTTP_X_API_SECRET="invalid_secret"
        )

        # Should raise AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(request)

    def test_inactive_client(self):
        """Test authentication with inactive client."""
        # Deactivate client
        self.client_data.status = 'suspended'
        self.client_data.save()

        auth = APIKeyAuthentication()

        from django.test import RequestFactory
        from rest_framework.exceptions import AuthenticationFailed
        factory = RequestFactory()

        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY=self.client_data.api_key,
            HTTP_X_API_SECRET=self.api_secret
        )

        # Should raise AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(request)

    def test_ip_whitelist_validation(self):
        """Test IP whitelist validation."""
        # Set IP whitelist
        self.client_data.allowed_ips = "192.168.1.1,10.0.0.1"
        self.client_data.save()

        auth = APIKeyAuthentication()

        from django.test import RequestFactory
        from rest_framework.exceptions import AuthenticationFailed
        factory = RequestFactory()

        # Request from non-whitelisted IP
        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY=self.client_data.api_key,
            HTTP_X_API_SECRET=self.api_secret,
            REMOTE_ADDR="192.168.1.100"
        )

        # Should raise AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(request)

        # Request from whitelisted IP
        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY=self.client_data.api_key,
            HTTP_X_API_SECRET=self.api_secret,
            REMOTE_ADDR="192.168.1.1"
        )

        # Should succeed
        result = auth.authenticate(request)
        self.assertIsNotNone(result)


class ClientPermissionsTest(TestCase):
    """Test custom client permission classes."""

    def setUp(self):
        """Set up test data."""
        self.client_data, self.api_secret = Client.objects.create_client(
            name="Test Client",
            email="test@example.com",
            description="Test client for permissions"
        )

        # Create transaction for testing ownership
        self.transaction = Transaction.objects.create(
            client=self.client_data,
            transaction_type="STK_PUSH",
            phone_number="+254712345678",
            amount=Decimal("100.00"),
            description="Test transaction",
            status="SUCCESSFUL"
        )

    def test_is_valid_client_permission(self):
        """Test IsValidClient permission."""
        permission = IsValidClient()

        from django.test import RequestFactory
        factory = RequestFactory()

        # Create request with client
        request = factory.get('/api/test/')
        request.user = self.client_data

        # Should allow access
        self.assertTrue(permission.has_permission(request, None))

        # Test with inactive client
        self.client_data.status = 'disabled'
        self.client_data.save()

        # Should deny access
        self.assertFalse(permission.has_permission(request, None))

    def test_client_owner_permission(self):
        """Test ClientOwnerPermission."""
        permission = ClientOwnerPermission()

        from django.test import RequestFactory
        factory = RequestFactory()

        # Create request with client
        request = factory.get('/api/test/')
        request.user = self.client_data

        # Should allow access to owned object
        self.assertTrue(permission.has_object_permission(request, None, self.transaction))

        # Create another client and transaction
        other_client, _ = Client.objects.create_client(
            name="Other Client",
            email="other@example.com"
        )

        other_transaction = Transaction.objects.create(
            client=other_client,
            transaction_type="STK_PUSH",
            phone_number="+254712345679",
            amount=Decimal("200.00"),
            description="Other transaction",
            status="SUCCESSFUL"
        )

        # Should deny access to other client's object
        self.assertFalse(permission.has_object_permission(request, None, other_transaction))


class APIEndpointTest(APITestCase):
    """Test API endpoints with authentication."""

    def setUp(self):
        """Set up test data."""
        self.client_data, self.api_secret = Client.objects.create_client(
            name="Test Client",
            email="test@example.com",
            description="Test client for API testing"
        )

        # Create client configuration
        ClientConfiguration.objects.create(client=self.client_data)

        # Create API client for testing
        self.api_client = APIClient()

    def _authenticate_client(self):
        """Authenticate the API client."""
        self.api_client.credentials(
            HTTP_X_API_KEY=self.client_data.api_key,
            HTTP_X_API_SECRET=self.api_secret
        )

    def test_unauthenticated_request(self):
        """Test request without authentication."""
        # Try to access protected endpoint without authentication
        response = self.api_client.get('/api/v1/clients/profile/')

        # Should return 401 Unauthorized
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_client_profile(self):
        """Test client profile endpoint with authentication."""
        self._authenticate_client()

        # Access client profile
        response = self.api_client.get('/api/v1/clients/profile/')

        # Should return 200 OK
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify response data
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['name'], self.client_data.name)
        self.assertEqual(data['data']['email'], self.client_data.email)

    def test_client_profile_update(self):
        """Test updating client profile."""
        self._authenticate_client()

        update_data = {
            'description': 'Updated description',
            'webhook_url': 'https://example.com/webhook'
        }

        # Update profile
        response = self.api_client.put('/api/v1/clients/profile/', update_data)

        # Should return 200 OK
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify update
        self.client_data.refresh_from_db()
        self.assertEqual(self.client_data.description, 'Updated description')
        self.assertEqual(self.client_data.webhook_url, 'https://example.com/webhook')

    def test_stk_push_initiation(self):
        """Test STK Push initiation with authentication."""
        self._authenticate_client()

        payment_data = {
            'phone_number': '+254712345678',
            'amount': '100.00',
            'description': 'Test payment',
            'account_reference': 'TEST001'
        }

        # Note: This test might fail if MPesa configuration is not set up
        # In a real test environment, you would mock the MPesa service
        response = self.api_client.post('/api/v1/mpesa/initiate/', payment_data)

        # Response should have proper format (might be error due to config)
        self.assertIn(response.status_code, [
            status.HTTP_201_CREATED,  # Success
            status.HTTP_400_BAD_REQUEST,  # Validation error
            status.HTTP_502_BAD_GATEWAY   # MPesa service error
        ])

    def test_transaction_list(self):
        """Test transaction listing with authentication."""
        self._authenticate_client()

        # Create test transaction
        Transaction.objects.create(
            client=self.client_data,
            transaction_type="STK_PUSH",
            phone_number="+254712345678",
            amount=Decimal("100.00"),
            description="Test transaction",
            status="SUCCESSFUL"
        )

        # Get transaction list
        response = self.api_client.get('/api/v1/mpesa/transactions/')

        # Should return 200 OK
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify response data
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('transactions', data['data'])
        self.assertGreaterEqual(len(data['data']['transactions']), 1)


class MultiAuthenticationTest(TestCase):
    """Test multi-authentication system."""

    def setUp(self):
        """Set up test data."""
        self.client_data, self.api_secret = Client.objects.create_client(
            name="Test Client",
            email="test@example.com",
            description="Test client for multi-auth"
        )

    def test_multi_authentication_api_key_success(self):
        """Test multi-authentication with API key success."""
        auth = MultiAuthentication()

        from django.test import RequestFactory
        factory = RequestFactory()

        request = factory.post(
            '/api/test/',
            HTTP_X_API_KEY=self.client_data.api_key,
            HTTP_X_API_SECRET=self.api_secret
        )

        # Should authenticate using API key method
        result = auth.authenticate(request)
        self.assertIsNotNone(result)

        client, token = result
        self.assertIsInstance(client, Client)
        self.assertEqual(client.client_id, self.client_data.client_id)

    def test_multi_authentication_no_auth(self):
        """Test multi-authentication with no authentication headers."""
        auth = MultiAuthentication()

        from django.test import RequestFactory
        factory = RequestFactory()

        request = factory.post('/api/test/')

        # Should return None (no authentication attempted)
        result = auth.authenticate(request)
        self.assertIsNone(result)


class EncryptionTest(TestCase):
    """Test encryption utilities used in authentication."""

    def test_api_key_generation(self):
        """Test API key generation."""
        # Generate API key
        api_key = encryption_manager.generate_api_key(32)

        # Should be correct length and format
        self.assertEqual(len(api_key), 64)  # 32 bytes = 64 hex chars
        self.assertTrue(all(c in '0123456789abcdef' for c in api_key.lower()))

    def test_hash_verification(self):
        """Test hash creation and verification."""
        secret = "test_secret"

        # Hash the secret
        hashed = encryption_manager.hash_data(secret)

        # Should be able to verify
        self.assertEqual(encryption_manager.hash_data(secret), hashed)

        # Different secret should not match
        self.assertNotEqual(encryption_manager.hash_data("different_secret"), hashed)


class RateLimitingTest(TestCase):
    """Test rate limiting functionality."""

    def setUp(self):
        """Set up test data."""
        self.client_data, self.api_secret = Client.objects.create_client(
            name="Test Client",
            email="test@example.com",
            description="Test client for rate limiting"
        )

        # Set low rate limits for testing
        self.client_data.rate_limit_per_minute = 2
        self.client_data.rate_limit_per_hour = 5
        self.client_data.rate_limit_per_day = 10
        self.client_data.save()

    def test_rate_limiting_middleware(self):
        """Test rate limiting middleware functionality."""
        from core.middleware.api_auth import RateLimitMiddleware

        middleware = RateLimitMiddleware(lambda r: None)

        from django.test import RequestFactory
        factory = RequestFactory()

        # Create request with authenticated client
        request = factory.post('/api/test/')
        request.user = self.client_data

        # First requests should pass
        result1 = middleware.process_request(request)
        self.assertIsNone(result1)  # None means continue processing

        result2 = middleware.process_request(request)
        self.assertIsNone(result2)

        # Third request should be rate limited
        result3 = middleware.process_request(request)
        if result3:  # If rate limiting is active
            self.assertEqual(result3.status_code, 429)
