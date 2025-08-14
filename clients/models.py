"""
Client management models for API key authentication and access control.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from core.utils.encryption import encryption_manager
import uuid
import logging

logger = logging.getLogger(__name__)


class ClientManager(models.Manager):
    """Custom manager for Client model."""

    def create_client(self, name, email, description="", **kwargs):
        """
        Create a new client with encrypted API credentials.

        Args:
            name (str): Client name
            email (str): Client email
            description (str): Client description
            **kwargs: Additional client fields

        Returns:
            Client: Created client instance
        """
        # Generate API key and secret
        api_key = encryption_manager.generate_api_key(32)
        api_secret = encryption_manager.generate_api_key(64)

        # Create client
        client = self.create(
            name=name,
            email=email,
            description=description,
            api_key=api_key,
            api_secret_hash=encryption_manager.hash_data(api_secret),
            **kwargs
        )

        # Log client creation
        logger.info(f"Created new client: {client.name} ({client.client_id})")

        return client, api_secret  # Return secret only during creation


class Client(models.Model):
    """
    Represents an API client that can access the payment gateway.
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('disabled', 'Disabled'),
    ]

    PLAN_CHOICES = [
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    ]

    # Basic Information
    client_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique client identifier"
    )
    name = models.CharField(
        max_length=255,
        help_text="Client business name"
    )
    email = models.EmailField(
        unique=True,
        help_text="Client contact email"
    )
    phone_number = models.CharField(
    max_length=20,
    default="254759104865",
    help_text="Client phone number"
    )

    description = models.TextField(
        blank=True,
        help_text="Description of the client's business"
    )

    # API Credentials
    api_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Public API key"
    )
    api_secret_hash = models.CharField(
        max_length=255,
        help_text="Hashed API secret for verification"
    )

    # Status and Configuration
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text="Client account status"
    )
    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default='free',
        help_text="Client subscription plan"
    )

    # Rate Limiting
    rate_limit_per_minute = models.PositiveIntegerField(
        default=60,
        help_text="API calls allowed per minute"
    )
    rate_limit_per_hour = models.PositiveIntegerField(
        default=1000,
        help_text="API calls allowed per hour"
    )
    rate_limit_per_day = models.PositiveIntegerField(
        default=10000,
        help_text="API calls allowed per day"
    )

    # Webhooks
    webhook_url = models.URLField(
        blank=True,
        null=True,
        help_text="Client webhook URL for notifications"
    )
    webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text="Secret for webhook signature verification"
    )

    # IP Whitelisting
    allowed_ips = models.TextField(
        blank=True,
        help_text="Comma-separated list of allowed IP addresses"
    )

    # Financial Information
    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        help_text="Client account balance"
    )
    total_transactions = models.PositiveIntegerField(
        default=0,
        help_text="Total number of transactions"
    )
    total_volume = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        help_text="Total transaction volume"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_api_call = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last API call"
    )

    # Django User Association (optional)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Associated Django user account"
    )

    objects = ClientManager()

    class Meta:
        db_table = 'clients'
        verbose_name = 'API Client'
        verbose_name_plural = 'API Clients'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.client_id})"

    def is_active(self):
        """Check if client is active."""
        return self.status == 'active'

    def verify_api_secret(self, secret):
        """Verify API secret against stored hash."""
        return encryption_manager.hash_data(secret) == self.api_secret_hash

    def is_ip_allowed(self, ip_address):
        """Check if IP address is whitelisted."""
        if not self.allowed_ips:
            return True  # No restrictions

        allowed_list = [ip.strip() for ip in self.allowed_ips.split(',')]
        return ip_address in allowed_list

    def update_last_api_call(self):
        """Update last API call timestamp."""
        self.last_api_call = timezone.now()
        self.save(update_fields=['last_api_call'])

    def get_allowed_ips_list(self):
        """Get list of allowed IP addresses."""
        if not self.allowed_ips:
            return []
        return [ip.strip() for ip in self.allowed_ips.split(',')]

    def add_allowed_ip(self, ip_address):
        """Add IP address to whitelist."""
        current_ips = self.get_allowed_ips_list()
        if ip_address not in current_ips:
            current_ips.append(ip_address)
            self.allowed_ips = ','.join(current_ips)
            self.save(update_fields=['allowed_ips'])

    def remove_allowed_ip(self, ip_address):
        """Remove IP address from whitelist."""
        current_ips = self.get_allowed_ips_list()
        if ip_address in current_ips:
            current_ips.remove(ip_address)
            self.allowed_ips = ','.join(current_ips)
            self.save(update_fields=['allowed_ips'])


class APIUsageLog(models.Model):
    """
    Tracks API usage for monitoring and rate limiting.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )
    endpoint = models.CharField(
        max_length=255,
        help_text="API endpoint accessed"
    )
    method = models.CharField(
        max_length=10,
        help_text="HTTP method used"
    )
    ip_address = models.GenericIPAddressField(
        help_text="Client IP address"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Client user agent"
    )
    request_size = models.PositiveIntegerField(
        default=0,
        help_text="Request size in bytes"
    )
    response_size = models.PositiveIntegerField(
        default=0,
        help_text="Response size in bytes"
    )
    response_time = models.PositiveIntegerField(
        default=0,
        help_text="Response time in milliseconds"
    )
    status_code = models.PositiveIntegerField(
        help_text="HTTP response status code"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if any"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    # Additional metadata
    request_id = models.UUIDField(
        default=uuid.uuid4,
        help_text="Unique request identifier"
    )

    class Meta:
        db_table = 'api_usage_logs'
        verbose_name = 'API Usage Log'
        verbose_name_plural = 'API Usage Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['client', 'timestamp']),
            models.Index(fields=['endpoint', 'timestamp']),
            models.Index(fields=['status_code', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.client.name} - {self.endpoint} - {self.timestamp}"


class ClientConfiguration(models.Model):
    """
    Stores client-specific configuration settings.
    """

    client = models.OneToOneField(
        Client,
        on_delete=models.CASCADE,
        related_name='configuration'
    )

    # MPesa Configuration
    mpesa_enabled = models.BooleanField(
        default=True,
        help_text="Enable MPesa payments for this client"
    )
    mpesa_shortcode = models.CharField(
        max_length=10,
        blank=True,
        help_text="Client's MPesa business shortcode"
    )
    mpesa_passkey = models.TextField(
        blank=True,
        help_text="Encrypted MPesa passkey"
    )

    # Transaction Limits
    min_transaction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1.00,
        help_text="Minimum transaction amount"
    )
    max_transaction_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100000.00,
        help_text="Maximum transaction amount"
    )
    daily_transaction_limit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=1000000.00,
        help_text="Daily transaction limit"
    )

    # Notification Settings
    email_notifications = models.BooleanField(
        default=True,
        help_text="Send email notifications"
    )
    sms_notifications = models.BooleanField(
        default=False,
        help_text="Send SMS notifications"
    )
    webhook_notifications = models.BooleanField(
        default=True,
        help_text="Send webhook notifications"
    )

    # Security Settings
    require_signature = models.BooleanField(
        default=True,
        help_text="Require request signature verification"
    )
    signature_algorithm = models.CharField(
        max_length=20,
        default='hmac-sha256',
        help_text="Signature algorithm"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_configurations'
        verbose_name = 'Client Configuration'
        verbose_name_plural = 'Client Configurations'

    def __str__(self):
        return f"Configuration for {self.client.name}"

    def encrypt_mpesa_passkey(self, passkey):
        """Encrypt and store MPesa passkey."""
        if passkey:
            self.mpesa_passkey = encryption_manager.encrypt_data(passkey)
            self.save(update_fields=['mpesa_passkey'])

    def decrypt_mpesa_passkey(self):
        """Decrypt MPesa passkey."""
        if self.mpesa_passkey:
            try:
                return encryption_manager.decrypt_data(self.mpesa_passkey)
            except Exception as e:
                logger.error(f"Failed to decrypt MPesa passkey: {e}")
                return None
        return None


class ClientAPIKey(models.Model):
    """
    Manages multiple API keys per client for different environments.
    """

    ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='api_keys'
    )
    name = models.CharField(
        max_length=255,
        help_text="API key name/description"
    )
    environment = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        default='sandbox'
    )
    api_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True
    )
    api_secret_hash = models.CharField(max_length=255)

    # Status and permissions
    is_active = models.BooleanField(default=True)
    permissions = models.JSONField(
        default=list,
        help_text="List of allowed permissions/scopes"
    )

    # Rate limiting (overrides client defaults)
    rate_limit_per_minute = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Override client rate limit per minute"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="API key expiration date"
    )

    class Meta:
        db_table = 'client_api_keys'
        verbose_name = 'Client API Key'
        verbose_name_plural = 'Client API Keys'
        unique_together = ['client', 'name', 'environment']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client.name} - {self.name} ({self.environment})"

    def is_expired(self):
        """Check if API key is expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    def verify_secret(self, secret):
        """Verify API secret."""
        return encryption_manager.hash_data(secret) == self.api_secret_hash

    def update_last_used(self):
        """Update last used timestamp."""
        self.last_used = timezone.now()
        self.save(update_fields=['last_used'])
