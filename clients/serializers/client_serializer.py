"""
Client serializers for API client management and authentication.
"""

from rest_framework import serializers
from decimal import Decimal
from clients.models import Client, ClientConfiguration, ClientAPIKey, APIUsageLog
from core.utils.encryption import encryption_manager
import re


class ClientRegistrationSerializer(serializers.Serializer):
    """Serializer for client registration."""

    name = serializers.CharField(
        max_length=255,
        help_text="Business name"
    )
    email = serializers.EmailField(
        help_text="Contact email address"
    )
    description = serializers.CharField(
        max_length=500,
        required=False,
        help_text="Business description"
    )
    plan = serializers.ChoiceField(
        choices=Client.PLAN_CHOICES,
        default='free',
        help_text="Subscription plan"
    )
    webhook_url = serializers.URLField(
        required=False,
        help_text="Webhook URL for notifications"
    )

    def validate_email(self, value):
        """Validate email uniqueness."""
        if Client.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered")
        return value

    def validate_name(self, value):
        """Validate business name."""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Business name must be at least 2 characters")
        return value.strip()


class ClientResponseSerializer(serializers.ModelSerializer):
    """Serializer for client profile responses."""

    api_key = serializers.CharField(read_only=True)
    client_id = serializers.UUIDField(read_only=True)
    total_transactions = serializers.IntegerField(read_only=True)
    total_volume = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    last_api_call = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Client
        fields = [
            'client_id', 'name', 'email', 'description', 'api_key',
            'status', 'plan', 'rate_limit_per_minute', 'rate_limit_per_hour',
            'rate_limit_per_day', 'webhook_url', 'balance', 'total_transactions',
            'total_volume', 'last_api_call', 'created_at'
        ]
        read_only_fields = [
            'client_id', 'api_key', 'balance', 'total_transactions',
            'total_volume', 'last_api_call', 'created_at'
        ]


class ClientRegistrationResponseSerializer(serializers.Serializer):
    """Serializer for client registration response with credentials."""

    client = ClientResponseSerializer(read_only=True)
    api_secret = serializers.CharField(
        read_only=True,
        help_text="API secret - store securely, won't be shown again"
    )
    message = serializers.CharField(read_only=True)


class ClientUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating client information."""

    class Meta:
        model = Client
        fields = [
            'name', 'description', 'webhook_url', 'webhook_secret'
        ]

    def validate_name(self, value):
        """Validate business name."""
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Business name must be at least 2 characters")
        return value.strip()


class APIKeyGenerationSerializer(serializers.Serializer):
    """Serializer for generating new API keys."""

    name = serializers.CharField(
        max_length=255,
        help_text="Name/description for the API key"
    )
    environment = serializers.ChoiceField(
        choices=ClientAPIKey.ENVIRONMENT_CHOICES,
        default='sandbox',
        help_text="Environment for the API key"
    )
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="List of permissions/scopes"
    )
    expires_at = serializers.DateTimeField(
        required=False,
        help_text="Optional expiration date"
    )

    def validate_name(self, value):
        """Validate API key name."""
        if len(value.strip()) < 3:
            raise serializers.ValidationError("API key name must be at least 3 characters")
        return value.strip()


class APIKeyResponseSerializer(serializers.Serializer):
    """Serializer for API key generation response."""

    api_key = serializers.CharField(read_only=True)
    api_secret = serializers.CharField(
        read_only=True,
        help_text="Store securely - won't be shown again"
    )
    name = serializers.CharField(read_only=True)
    environment = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True, allow_null=True)


class APIKeyListSerializer(serializers.ModelSerializer):
    """Serializer for listing API keys."""

    class Meta:
        model = ClientAPIKey
        fields = [
            'api_key', 'name', 'environment', 'is_active',
            'permissions', 'created_at', 'last_used', 'expires_at'
        ]
        read_only_fields = ['api_key', 'created_at', 'last_used']


class ClientConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for client configuration."""

    class Meta:
        model = ClientConfiguration
        fields = [
            'mpesa_enabled', 'mpesa_shortcode', 'min_transaction_amount',
            'max_transaction_amount', 'daily_transaction_limit',
            'email_notifications', 'sms_notifications', 'webhook_notifications',
            'require_signature', 'signature_algorithm'
        ]

    def validate_min_transaction_amount(self, value):
        """Validate minimum transaction amount."""
        if value < Decimal('1.00'):
            raise serializers.ValidationError("Minimum amount cannot be less than KES 1.00")
        return value

    def validate_max_transaction_amount(self, value):
        """Validate maximum transaction amount."""
        if value > Decimal('150000.00'):
            raise serializers.ValidationError("Maximum amount cannot exceed KES 150,000.00")
        return value

    def validate(self, data):
        """Validate configuration data."""
        min_amount = data.get('min_transaction_amount')
        max_amount = data.get('max_transaction_amount')

        if min_amount and max_amount and min_amount >= max_amount:
            raise serializers.ValidationError(
                "Minimum amount must be less than maximum amount"
            )

        return data


class IPWhitelistSerializer(serializers.Serializer):
    """Serializer for IP whitelist management."""

    ip_addresses = serializers.ListField(
        child=serializers.IPAddressField(),
        help_text="List of allowed IP addresses"
    )

    def validate_ip_addresses(self, value):
        """Validate IP addresses."""
        if len(value) > 50:
            raise serializers.ValidationError("Maximum 50 IP addresses allowed")

        # Remove duplicates while preserving order
        unique_ips = []
        for ip in value:
            if ip not in unique_ips:
                unique_ips.append(ip)

        return unique_ips


class UsageStatsSerializer(serializers.Serializer):
    """Serializer for client usage statistics."""

    period_start = serializers.DateTimeField(read_only=True)
    period_end = serializers.DateTimeField(read_only=True)
    total_requests = serializers.IntegerField(read_only=True)
    successful_requests = serializers.IntegerField(read_only=True)
    failed_requests = serializers.IntegerField(read_only=True)
    average_response_time = serializers.FloatField(read_only=True)
    total_data_transferred = serializers.IntegerField(read_only=True)
    endpoints_usage = serializers.DictField(read_only=True)
    daily_breakdown = serializers.ListField(read_only=True)


class APIUsageLogSerializer(serializers.ModelSerializer):
    """Serializer for API usage logs."""

    class Meta:
        model = APIUsageLog
        fields = [
            'request_id', 'endpoint', 'method', 'ip_address',
            'request_size', 'response_size', 'response_time',
            'status_code', 'error_message', 'timestamp'
        ]
        read_only_fields = ['request_id', 'timestamp']


class ClientStatsSerializer(serializers.Serializer):
    """Serializer for comprehensive client statistics."""

    client_info = ClientResponseSerializer(read_only=True)
    transaction_stats = serializers.DictField(read_only=True)
    usage_stats = UsageStatsSerializer(read_only=True)
    api_keys_count = serializers.IntegerField(read_only=True)
    last_activity = serializers.DateTimeField(read_only=True)


class WebhookTestSerializer(serializers.Serializer):
    """Serializer for webhook testing."""

    webhook_url = serializers.URLField(
        help_text="Webhook URL to test"
    )
    event_type = serializers.ChoiceField(
        choices=[
            ('payment.successful', 'Payment Successful'),
            ('payment.failed', 'Payment Failed'),
            ('payment.pending', 'Payment Pending'),
        ],
        default='payment.successful',
        help_text="Event type to simulate"
    )
    test_data = serializers.DictField(
        required=False,
        help_text="Optional test data payload"
    )


class WebhookTestResponseSerializer(serializers.Serializer):
    """Serializer for webhook test response."""

    success = serializers.BooleanField(read_only=True)
    status_code = serializers.IntegerField(read_only=True)
    response_time_ms = serializers.FloatField(read_only=True)
    response_headers = serializers.DictField(read_only=True)
    response_body = serializers.CharField(read_only=True)
    error_message = serializers.CharField(read_only=True, allow_null=True)


class ClientSearchSerializer(serializers.Serializer):
    """Serializer for client search filters."""

    name = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    status = serializers.ChoiceField(
        choices=Client.STATUS_CHOICES,
        required=False
    )
    plan = serializers.ChoiceField(
        choices=Client.PLAN_CHOICES,
        required=False
    )
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    has_transactions = serializers.BooleanField(required=False)


class BulkClientActionSerializer(serializers.Serializer):
    """Serializer for bulk client actions."""

    client_ids = serializers.ListField(
        child=serializers.UUIDField(),
        max_length=100,
        help_text="List of client IDs (max 100)"
    )
    action = serializers.ChoiceField(
        choices=[
            ('activate', 'Activate'),
            ('suspend', 'Suspend'),
            ('disable', 'Disable'),
        ],
        help_text="Action to perform"
    )
    reason = serializers.CharField(
        max_length=255,
        required=False,
        help_text="Reason for the action"
    )

    def validate_client_ids(self, value):
        """Validate client IDs."""
        if len(value) == 0:
            raise serializers.ValidationError("At least one client ID is required")

        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate client IDs found")

        return value


class ClientExportSerializer(serializers.Serializer):
    """Serializer for client data export."""

    format = serializers.ChoiceField(
        choices=[('csv', 'CSV'), ('excel', 'Excel'), ('json', 'JSON')],
        default='csv'
    )
    include_transactions = serializers.BooleanField(default=False)
    include_usage_logs = serializers.BooleanField(default=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)

    def validate(self, data):
        """Validate export parameters."""
        if data.get('date_from') and data.get('date_to'):
            if data['date_from'] >= data['date_to']:
                raise serializers.ValidationError(
                    "Start date must be before end date"
                )

        return data


class ClientNotificationSerializer(serializers.Serializer):
    """Serializer for sending notifications to clients."""

    client_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Specific client IDs (empty for all)"
    )
    subject = serializers.CharField(max_length=255)
    message = serializers.CharField(max_length=2000)
    notification_type = serializers.ChoiceField(
        choices=[
            ('email', 'Email'),
            ('webhook', 'Webhook'),
            ('both', 'Both Email and Webhook'),
        ],
        default='email'
    )
    priority = serializers.ChoiceField(
        choices=[
            ('low', 'Low'),
            ('normal', 'Normal'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        default='normal'
    )
