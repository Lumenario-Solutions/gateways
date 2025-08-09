"""
MPesa payment models for transaction tracking and credential management.
"""

from django.db import models
from django.utils import timezone
from clients.models import Client
from core.utils.encryption import encryption_manager
from core.utils.phone import normalize_phone_number, PhoneNumberError
import uuid
import json
import logging

logger = logging.getLogger(__name__)


class MpesaCredentialsManager(models.Manager):
    """Custom manager for MPesa credentials."""

    def get_active_credentials(self, environment='sandbox'):
        """Get active MPesa credentials for environment."""
        try:
            return self.get(environment=environment, is_active=True)
        except self.model.DoesNotExist:
            logger.error(f"No active MPesa credentials found for environment: {environment}")
            return None


class MpesaCredentials(models.Model):
    """
    Stores encrypted MPesa API credentials.
    """

    ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('live', 'Live'),
    ]

    name = models.CharField(
        max_length=255,
        help_text="Credential set name"
    )
    environment = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        default='sandbox'
    )

    # Encrypted credentials
    consumer_key = models.TextField(
        help_text="Encrypted consumer key"
    )
    consumer_secret = models.TextField(
        help_text="Encrypted consumer secret"
    )
    business_shortcode = models.CharField(
        max_length=10,
        help_text="Business shortcode"
    )
    passkey = models.TextField(
        help_text="Encrypted online passkey"
    )
    initiator_name = models.CharField(
        max_length=255,
        help_text="Initiator name for B2C/reversal transactions"
    )
    security_credential = models.TextField(
        help_text="Encrypted security credential"
    )

    # API URLs (automatically set based on environment)
    base_url = models.URLField(
        help_text="Base URL for MPesa API"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether these credentials are active"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MpesaCredentialsManager()

    class Meta:
        db_table = 'mpesa_credentials'
        verbose_name = 'MPesa Credentials'
        verbose_name_plural = 'MPesa Credentials'
        unique_together = ['environment', 'is_active']

    def __str__(self):
        return f"{self.name} ({self.environment})"

    def save(self, *args, **kwargs):
        """Override save to set base URL and encrypt credentials."""
        # Set base URL based on environment
        if self.environment == 'live':
            self.base_url = 'https://api.safaricom.co.ke'
        else:
            self.base_url = 'https://sandbox.safaricom.co.ke'

        super().save(*args, **kwargs)

    def set_credentials(self, consumer_key, consumer_secret, passkey, security_credential):
        """Encrypt and store credentials."""
        self.consumer_key = encryption_manager.encrypt_data(consumer_key)
        self.consumer_secret = encryption_manager.encrypt_data(consumer_secret)
        self.passkey = encryption_manager.encrypt_data(passkey)
        self.security_credential = encryption_manager.encrypt_data(security_credential)

    def get_decrypted_credentials(self):
        """Get decrypted credentials for API calls."""
        try:
            return {
                'consumer_key': encryption_manager.decrypt_data(self.consumer_key),
                'consumer_secret': encryption_manager.decrypt_data(self.consumer_secret),
                'business_shortcode': self.business_shortcode,
                'passkey': encryption_manager.decrypt_data(self.passkey),
                'initiator_name': self.initiator_name,
                'security_credential': encryption_manager.decrypt_data(self.security_credential),
                'base_url': self.base_url,
            }
        except Exception as e:
            logger.error(f"Failed to decrypt MPesa credentials: {e}")
            return None


class TransactionManager(models.Manager):
    """Custom manager for Transaction model."""

    def create_stk_push_transaction(self, client, phone_number, amount, description, reference=None):
        """Create a new STK push transaction."""
        try:
            # Normalize phone number
            normalized_phone = normalize_phone_number(phone_number)

            transaction = self.create(
                client=client,
                transaction_type='STK_PUSH',
                phone_number=normalized_phone,
                amount=amount,
                description=description,
                reference=reference or f"TXN_{uuid.uuid4().hex[:8].upper()}",
                status='PENDING'
            )

            logger.info(f"Created STK push transaction: {transaction.transaction_id}")
            return transaction

        except PhoneNumberError as e:
            logger.error(f"Invalid phone number for STK push: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create STK push transaction: {e}")
            raise

    def get_transaction_by_checkout_request_id(self, checkout_request_id):
        """Get transaction by MPesa checkout request ID."""
        try:
            return self.get(checkout_request_id=checkout_request_id)
        except self.model.DoesNotExist:
            return None


class Transaction(models.Model):
    """
    Tracks all MPesa transactions.
    """

    TRANSACTION_TYPES = [
        ('STK_PUSH', 'STK Push'),
        ('B2C', 'Business to Customer'),
        ('B2B', 'Business to Business'),
        ('C2B_PAYBILL', 'Customer to Business - Paybill'),
        ('C2B_BUYGOODS', 'Customer to Business - Buy Goods'),
        ('REVERSAL', 'Transaction Reversal'),
        ('BALANCE_INQUIRY', 'Account Balance'),
        ('TRANSACTION_STATUS', 'Transaction Status'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESSFUL', 'Successful'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('TIMEOUT', 'Timeout'),
        ('REVERSED', 'Reversed'),
        ('PROCESSING', 'Processing'),
    ]

    # Primary keys and relationships
    transaction_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='transactions'
    )

    # Transaction details
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES
    )
    phone_number = models.CharField(
        max_length=15,
        help_text="Normalized phone number (254XXXXXXXXX)"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Transaction amount"
    )
    description = models.CharField(
        max_length=255,
        help_text="Transaction description"
    )
    reference = models.CharField(
        max_length=100,
        help_text="Client transaction reference"
    )

    # MPesa specific fields
    checkout_request_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text="MPesa checkout request ID"
    )
    merchant_request_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="MPesa merchant request ID"
    )
    mpesa_receipt_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="MPesa transaction receipt number"
    )
    transaction_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="MPesa transaction timestamp"
    )

    # Status and tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    response_code = models.CharField(
        max_length=10,
        blank=True,
        help_text="MPesa response code"
    )
    response_description = models.TextField(
        blank=True,
        help_text="MPesa response description"
    )

    # Callback information
    callback_received = models.BooleanField(
        default=False,
        help_text="Whether callback has been received"
    )
    callback_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw callback data from MPesa"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Additional metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Client user agent"
    )

    objects = TransactionManager()

    class Meta:
        db_table = 'mpesa_transactions'
        verbose_name = 'MPesa Transaction'
        verbose_name_plural = 'MPesa Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['phone_number', 'created_at']),
            models.Index(fields=['mpesa_receipt_number']),
            models.Index(fields=['checkout_request_id']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.phone_number} - {self.amount}"

    def update_status(self, status, response_code=None, response_description=None):
        """Update transaction status."""
        self.status = status
        if response_code:
            self.response_code = response_code
        if response_description:
            self.response_description = response_description
        self.updated_at = timezone.now()
        self.save(update_fields=['status', 'response_code', 'response_description', 'updated_at'])

        logger.info(f"Transaction {self.transaction_id} status updated to {status}")

    def process_callback(self, callback_data):
        """Process MPesa callback data."""
        try:
            self.callback_received = True
            self.callback_data = callback_data

            # Extract callback information
            if 'Body' in callback_data and 'stkCallback' in callback_data['Body']:
                stk_callback = callback_data['Body']['stkCallback']

                # Update basic fields
                self.merchant_request_id = stk_callback.get('MerchantRequestID', '')
                self.checkout_request_id = stk_callback.get('CheckoutRequestID', '')
                self.response_code = stk_callback.get('ResultCode', '')
                self.response_description = stk_callback.get('ResultDesc', '')

                # Process based on result code
                if self.response_code == '0':
                    self.status = 'SUCCESSFUL'

                    # Extract callback items if successful
                    if 'CallbackMetadata' in stk_callback:
                        metadata = stk_callback['CallbackMetadata']
                        if 'Item' in metadata:
                            for item in metadata['Item']:
                                name = item.get('Name', '')
                                value = item.get('Value', '')

                                if name == 'MpesaReceiptNumber':
                                    self.mpesa_receipt_number = value
                                elif name == 'TransactionDate':
                                    # Convert MPesa date format to datetime
                                    try:
                                        self.transaction_date = timezone.datetime.strptime(
                                            str(value), '%Y%m%d%H%M%S'
                                        ).replace(tzinfo=timezone.utc)
                                    except ValueError:
                                        logger.warning(f"Invalid transaction date format: {value}")
                else:
                    self.status = 'FAILED'

            self.save()
            logger.info(f"Processed callback for transaction {self.transaction_id}")

        except Exception as e:
            logger.error(f"Failed to process callback for transaction {self.transaction_id}: {e}")
            raise

    def is_successful(self):
        """Check if transaction is successful."""
        return self.status == 'SUCCESSFUL'

    def is_pending(self):
        """Check if transaction is pending."""
        return self.status == 'PENDING'

    def is_failed(self):
        """Check if transaction is failed."""
        return self.status == 'FAILED'


class CallbackLog(models.Model):
    """
    Logs all callback requests from MPesa for audit purposes.
    """

    CALLBACK_TYPES = [
        ('STK_PUSH', 'STK Push Callback'),
        ('C2B_VALIDATION', 'C2B Validation'),
        ('C2B_CONFIRMATION', 'C2B Confirmation'),
        ('B2C', 'B2C Callback'),
        ('REVERSAL', 'Reversal Callback'),
        ('BALANCE_INQUIRY', 'Balance Inquiry Callback'),
        ('TRANSACTION_STATUS', 'Transaction Status Callback'),
    ]

    log_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='callback_logs'
    )

    callback_type = models.CharField(
        max_length=20,
        choices=CALLBACK_TYPES
    )

    # Request details
    ip_address = models.GenericIPAddressField(
        help_text="Source IP address"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="User agent from callback request"
    )
    headers = models.JSONField(
        default=dict,
        help_text="HTTP headers from callback request"
    )

    # Callback data
    raw_data = models.JSONField(
        help_text="Raw callback data"
    )
    processed_successfully = models.BooleanField(
        default=False,
        help_text="Whether callback was processed successfully"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )

    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When callback was processed"
    )

    class Meta:
        db_table = 'mpesa_callback_logs'
        verbose_name = 'MPesa Callback Log'
        verbose_name_plural = 'MPesa Callback Logs'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['callback_type', 'received_at']),
            models.Index(fields=['processed_successfully', 'received_at']),
        ]

    def __str__(self):
        return f"{self.callback_type} - {self.received_at}"

    def mark_as_processed(self, success=True, error_message=None):
        """Mark callback as processed."""
        self.processed_successfully = success
        self.processed_at = timezone.now()
        if error_message:
            self.error_message = error_message
        self.save(update_fields=['processed_successfully', 'processed_at', 'error_message'])


class AccessToken(models.Model):
    """
    Caches MPesa access tokens to avoid frequent API calls.
    """

    environment = models.CharField(
        max_length=20,
        choices=MpesaCredentials.ENVIRONMENT_CHOICES,
        unique=True
    )
    access_token = models.TextField(
        help_text="Encrypted access token"
    )
    expires_at = models.DateTimeField(
        help_text="Token expiration time"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mpesa_access_tokens'
        verbose_name = 'MPesa Access Token'
        verbose_name_plural = 'MPesa Access Tokens'

    def __str__(self):
        return f"Access Token ({self.environment})"

    def is_expired(self):
        """Check if token is expired."""
        return timezone.now() >= self.expires_at

    def set_token(self, token, expires_in_seconds):
        """Encrypt and store access token."""
        self.access_token = encryption_manager.encrypt_data(token)
        self.expires_at = timezone.now() + timezone.timedelta(seconds=expires_in_seconds - 60)  # 60s buffer
        self.save()

    def get_token(self):
        """Get decrypted access token."""
        if self.is_expired():
            return None

        try:
            return encryption_manager.decrypt_data(self.access_token)
        except Exception as e:
            logger.error(f"Failed to decrypt access token: {e}")
            return None


class MpesaConfiguration(models.Model):
    """
    Global MPesa configuration settings.
    """

    # Callback URLs
    stk_callback_url = models.URLField(
        help_text="STK Push callback URL"
    )
    validation_url = models.URLField(
        help_text="C2B validation URL"
    )
    confirmation_url = models.URLField(
        help_text="C2B confirmation URL"
    )

    # Timeout settings
    stk_timeout_seconds = models.PositiveIntegerField(
        default=300,
        help_text="STK push timeout in seconds"
    )
    api_timeout_seconds = models.PositiveIntegerField(
        default=30,
        help_text="API request timeout in seconds"
    )

    # Retry settings
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of retries for failed requests"
    )
    retry_delay_seconds = models.PositiveIntegerField(
        default=5,
        help_text="Delay between retries in seconds"
    )

    # Feature flags
    enable_stk_push = models.BooleanField(
        default=True,
        help_text="Enable STK Push functionality"
    )
    enable_c2b = models.BooleanField(
        default=True,
        help_text="Enable C2B functionality"
    )
    enable_b2c = models.BooleanField(
        default=False,
        help_text="Enable B2C functionality"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mpesa_configuration'
        verbose_name = 'MPesa Configuration'
        verbose_name_plural = 'MPesa Configurations'

    def __str__(self):
        return f"MPesa Configuration (Updated: {self.updated_at})"

    @classmethod
    def get_config(cls):
        """Get or create configuration instance."""
        config, created = cls.objects.get_or_create(
            id=1,
            defaults={
                'stk_callback_url': 'https://lumenario.pythonanywhere.com/api/v1/mpesa/callback/',
                'validation_url': 'https://lumenario.pythonanywhere.com/api/v1/mpesa/validate/',
                'confirmation_url': 'https://lumenario.pythonanywhere.com/api/v1/mpesa/confirm/',
            }
        )
        return config
