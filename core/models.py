from django.db import models
from django.utils import timezone
from clients.models import Client
from core.utils.encryption import encryption_manager
import uuid
import logging

logger = logging.getLogger(__name__)


class ClientEnvironmentVariableManager(models.Manager):
    """Custom manager for ClientEnvironmentVariable model."""

    def get_variable(self, client, variable_type):
        """Get environment variable for client and type."""
        try:
            return self.get(client=client, variable_type=variable_type, is_active=True)
        except self.model.DoesNotExist:
            return None

    def set_variable(self, client, variable_type, variable_value, description=""):
        """Set or update environment variable for client."""
        try:
            # Check if variable already exists
            existing_var = self.filter(
                client=client,
                variable_type=variable_type,
                is_active=True
            ).first()

            if existing_var:
                # Update existing
                existing_var.set_encrypted_value(variable_value)
                existing_var.description = description
                existing_var.save()
                return existing_var
            else:
                # Create new
                env_var = self.create(
                    client=client,
                    variable_type=variable_type,
                    description=description,
                    is_active=True
                )
                env_var.set_encrypted_value(variable_value)
                env_var.save()
                return env_var
        except Exception as e:
            logger.error(f"Error setting environment variable: {e}")
            raise


class ClientEnvironmentVariable(models.Model):
    """
    Stores encrypted environment variables specific to each client.
    """

    ENV_VARIABLE_TYPES = [
        ('RESEND_API_KEY', 'Resend API Key'),
        ('MESSAGE_API_URL', 'Message API URL'),
        ('MESSAGE_API_KEY', 'Message API Key'),
        ('MPESA_PAYBILL', 'MPesa Paybill Number'),
        ('MPESA_SHORTCODE', 'MPesa Business Shortcode'),
        ('MPESA_TILL_NUMBER', 'MPesa Till Number'),
        ('WEBHOOK_SECRET', 'Webhook Secret'),
        ('CUSTOM', 'Custom Variable'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='environment_variables',
        help_text="Client who owns this environment variable"
    )
    variable_type = models.CharField(
        max_length=50,
        choices=ENV_VARIABLE_TYPES,
        help_text="Type of environment variable"
    )
    custom_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Custom name for CUSTOM type variables"
    )
    encrypted_value = models.TextField(
        help_text="Encrypted environment variable value"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the environment variable"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this variable is active"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ClientEnvironmentVariableManager()

    class Meta:
        db_table = 'client_environment_variables'
        verbose_name = 'Client Environment Variable'
        verbose_name_plural = 'Client Environment Variables'
        unique_together = ['client', 'variable_type', 'custom_name', 'is_active']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client.name} - {self.get_variable_name()}"

    def get_variable_name(self):
        """Get the variable name (type or custom name)."""
        if self.variable_type == 'CUSTOM' and self.custom_name:
            return self.custom_name
        return self.variable_type

    def set_encrypted_value(self, value):
        """Encrypt and store the variable value."""
        self.encrypted_value = encryption_manager.encrypt_data(str(value))

    def get_decrypted_value(self):
        """Get decrypted variable value."""
        try:
            return encryption_manager.decrypt_data(self.encrypted_value)
        except Exception as e:
            logger.error(f"Failed to decrypt environment variable {self.id}: {e}")
            return None

    def save(self, *args, **kwargs):
        """Override save to enforce uniqueness."""
        if self.is_active:
            # Deactivate other active variables of the same type for this client
            ClientEnvironmentVariable.objects.filter(
                client=self.client,
                variable_type=self.variable_type,
                custom_name=self.custom_name,
                is_active=True
            ).exclude(id=self.id).update(is_active=False)

        super().save(*args, **kwargs)


class NotificationManager(models.Manager):
    """Custom manager for Notification model."""

    def create_notification(self, client, notification_type, title, message,
                          reference_id=None, metadata=None):
        """Create a new notification."""
        try:
            notification = self.create(
                client=client,
                notification_type=notification_type,
                title=title,
                message=message,
                reference_id=reference_id,
                metadata=metadata or {},
                status='PENDING'
            )
            logger.info(f"Created notification for client {client.name}: {notification.id}")
            return notification
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            raise

    def get_unread_count(self, client):
        """Get count of unread notifications for client."""
        return self.filter(client=client, is_read=False).count()


class Notification(models.Model):
    """
    Stores notifications for clients.
    """

    NOTIFICATION_TYPES = [
        ('CLIENT_CREATED', 'Client Created'),
        ('CLIENT_UPDATED', 'Client Updated'),
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('PAYMENT_FAILED', 'Payment Failed'),
        ('TRANSACTION_SUCCESS', 'Transaction Successful'),
        ('TRANSACTION_FAILED', 'Transaction Failed'),
        ('MPESA_CREDENTIALS_UPDATED', 'MPesa Credentials Updated'),
        ('ENVIRONMENT_VARIABLE_UPDATED', 'Environment Variable Updated'),
        ('SYSTEM_ALERT', 'System Alert'),
        ('WEBHOOK_FAILED', 'Webhook Failed'),
        ('API_LIMIT_REACHED', 'API Limit Reached'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('DELIVERED', 'Delivered'),
    ]

    CHANNEL_CHOICES = [
        ('EMAIL', 'Email'),
        ('WHATSAPP', 'WhatsApp'),
        ('SMS', 'SMS'),
        ('WEBHOOK', 'Webhook'),
        ('IN_APP', 'In-App'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="Client who receives this notification"
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        help_text="Type of notification"
    )
    title = models.CharField(
        max_length=255,
        help_text="Notification title"
    )
    message = models.TextField(
        help_text="Notification message content"
    )

    # Delivery tracking
    channels_sent = models.JSONField(
        default=list,
        help_text="List of channels where notification was sent"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        help_text="Notification delivery status"
    )

    # Reference and metadata
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Reference ID (e.g., transaction_id, client_id)"
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Additional metadata for the notification"
    )

    # Read status
    is_read = models.BooleanField(
        default=False,
        help_text="Whether notification has been read"
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When notification was read"
    )

    # Delivery attempts
    email_sent = models.BooleanField(default=False)
    whatsapp_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if delivery failed"
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to send the notification (for scheduled notifications)"
    )

    objects = NotificationManager()

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['notification_type', 'created_at']),
            models.Index(fields=['is_read', 'client']),
            models.Index(fields=['status', 'scheduled_for']),
        ]

    def __str__(self):
        return f"{self.client.name} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_channel_sent(self, channel, success=True, error_message=None):
        """Mark a channel as sent."""
        channel = channel.upper()

        if success:
            if channel not in self.channels_sent:
                self.channels_sent.append(channel)

            if channel == 'EMAIL':
                self.email_sent = True
                self.email_sent_at = timezone.now()
            elif channel == 'WHATSAPP':
                self.whatsapp_sent = True
                self.whatsapp_sent_at = timezone.now()

            # Update overall status
            if self.status == 'PENDING':
                self.status = 'SENT'
        else:
            self.retry_count += 1
            if error_message:
                self.error_message = error_message

            # Mark as failed if too many retries
            if self.retry_count >= 3:
                self.status = 'FAILED'

        self.save()

    def get_client_hashtag(self):
        """Generate client hashtag for messages."""
        return f"#{self.client.name.replace(' ', '').lower()}"
