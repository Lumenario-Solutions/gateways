"""
Django signals for automatic activity tracking and notifications.
Tracks all model CRUD operations and triggers notifications for important events.
"""

import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from clients.models import Client, ClientConfiguration, APIUsageLog
from mpesa.models import Transaction, MpesaCredentials, CallbackLog
from core.models import Notification, ClientEnvironmentVariable, ActivityLog
from core.utils.notification_service import (
    notify_payment_received,
    notify_payment_failed,
    send_notification
)
import json

logger = logging.getLogger(__name__)


def get_client_from_request():
    """Get client from current request context."""
    # This is a simplified version - in production, you'd want to use
    # threading.local or request middleware to get the current client
    return None


def get_current_user():
    """Get current user from request context."""
    # This is a simplified version - in production, you'd want to use
    # threading.local or request middleware to get the current user
    return None


def get_current_ip():
    """Get current IP address from request context."""
    # This is a simplified version - in production, you'd want to use
    # threading.local or request middleware to get the current IP
    return None


def safe_model_to_dict(instance, exclude_fields=None):
    """Safely convert model instance to dictionary for logging."""
    exclude_fields = exclude_fields or ['password', 'secret', 'key', 'token']

    try:
        data = {}
        for field in instance._meta.fields:
            field_name = field.name
            if any(excl in field_name.lower() for excl in exclude_fields):
                data[field_name] = '[REDACTED]'
            else:
                value = getattr(instance, field_name, None)
                if value is not None:
                    # Convert non-serializable types
                    if hasattr(value, 'isoformat'):  # datetime
                        data[field_name] = value.isoformat()
                    elif hasattr(value, '__str__'):
                        data[field_name] = str(value)
                    else:
                        data[field_name] = value
        return data
    except Exception as e:
        logger.warning(f"Failed to convert model to dict: {e}")
        return {'error': 'Failed to serialize model data'}


# Client Management Signals
@receiver(post_save, sender=Client)
def track_client_save(sender, instance, created, **kwargs):
    """Track client creation and updates."""
    try:
        if created:
            # Client created
            ActivityLog.objects.log_client_activity(
                client=instance,
                activity_type='CLIENT_CREATED',
                description=f"New client created: {instance.name}",
                metadata={
                    'client_data': safe_model_to_dict(instance),
                    'plan': instance.plan,
                    'status': instance.status
                }
            )

            # Send welcome notification
            try:
                from core.utils.notification_service import notify_client_created
                notify_client_created(instance)
            except Exception as e:
                logger.error(f"Failed to send client creation notification: {e}")

        else:
            # Client updated
            ActivityLog.objects.log_client_activity(
                client=instance,
                activity_type='CLIENT_UPDATED',
                description=f"Client updated: {instance.name}",
                metadata={'client_data': safe_model_to_dict(instance)}
            )

            # Check if status changed
            if hasattr(instance, '_original_status') and instance._original_status != instance.status:
                ActivityLog.objects.log_client_activity(
                    client=instance,
                    activity_type='CLIENT_STATUS_CHANGED',
                    description=f"Client status changed from {instance._original_status} to {instance.status}",
                    metadata={
                        'old_status': instance._original_status,
                        'new_status': instance.status
                    }
                )

    except Exception as e:
        logger.error(f"Error in client save signal: {e}")


@receiver(pre_save, sender=Client)
def store_original_client_status(sender, instance, **kwargs):
    """Store original client status before save."""
    try:
        if instance.pk:
            try:
                original = Client.objects.get(pk=instance.pk)
                instance._original_status = original.status
            except Client.DoesNotExist:
                instance._original_status = None
    except Exception as e:
        logger.error(f"Error storing original client status: {e}")


@receiver(post_delete, sender=Client)
def track_client_deletion(sender, instance, **kwargs):
    """Track client deletion."""
    try:
        ActivityLog.objects.log_system_activity(
            activity_type='CLIENT_DELETED',
            description=f"Client deleted: {instance.name}",
            metadata={'client_data': safe_model_to_dict(instance)}
        )
    except Exception as e:
        logger.error(f"Error in client deletion signal: {e}")


# Transaction Signals
@receiver(post_save, sender=Transaction)
def track_transaction_save(sender, instance, created, **kwargs):
    """Track transaction creation and updates with notifications."""
    try:
        if created:
            # Transaction created
            ActivityLog.objects.log_payment_activity(
                transaction=instance,
                activity_type='TRANSACTION_CREATED',
                description=f"New transaction created: {instance.transaction_type} for {instance.amount}",
                metadata={
                    'transaction_data': safe_model_to_dict(instance),
                    'amount': str(instance.amount),
                    'phone_number': instance.phone_number
                }
            )

            # Log payment initiated
            ActivityLog.objects.log_payment_activity(
                transaction=instance,
                activity_type='PAYMENT_INITIATED',
                description=f"Payment initiated: KES {instance.amount} to {instance.phone_number}",
                metadata={'initial_status': instance.status}
            )

            # Send payment initiated notification
            try:
                send_notification(
                    client=instance.client,
                    notification_type='PAYMENT_INITIATED',
                    title='Payment Initiated',
                    message=f'Payment of KES {instance.amount} has been initiated to {instance.phone_number}',
                    reference_id=str(instance.transaction_id),
                    metadata={
                        'amount': str(instance.amount),
                        'phone_number': instance.phone_number,
                        'transaction_id': str(instance.transaction_id),
                        'transaction_type': instance.transaction_type
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send payment initiated notification: {e}")

        else:
            # Transaction updated
            ActivityLog.objects.log_payment_activity(
                transaction=instance,
                activity_type='TRANSACTION_UPDATED',
                description=f"Transaction updated: {instance.transaction_id}",
                metadata={'transaction_data': safe_model_to_dict(instance)}
            )

            # Check if status changed
            if hasattr(instance, '_original_status') and instance._original_status != instance.status:
                ActivityLog.objects.log_payment_activity(
                    transaction=instance,
                    activity_type='TRANSACTION_STATUS_CHANGED',
                    description=f"Transaction status changed from {instance._original_status} to {instance.status}",
                    metadata={
                        'old_status': instance._original_status,
                        'new_status': instance.status
                    }
                )

                # Handle status-specific notifications and logging
                if instance.status == 'SUCCESSFUL':
                    ActivityLog.objects.log_payment_activity(
                        transaction=instance,
                        activity_type='PAYMENT_SUCCESSFUL',
                        description=f"Payment successful: KES {instance.amount}",
                        metadata={'receipt_number': instance.mpesa_receipt_number}
                    )

                    # Send success notification
                    try:
                        notify_payment_received(instance.client, instance)
                    except Exception as e:
                        logger.error(f"Failed to send payment success notification: {e}")

                elif instance.status == 'FAILED':
                    ActivityLog.objects.log_payment_activity(
                        transaction=instance,
                        activity_type='PAYMENT_FAILED',
                        description=f"Payment failed: KES {instance.amount}",
                        metadata={'error_reason': instance.response_description},
                        level='WARNING'
                    )

                    # Send failure notification
                    try:
                        notify_payment_failed(instance.client, instance)
                    except Exception as e:
                        logger.error(f"Failed to send payment failure notification: {e}")

                elif instance.status == 'CANCELLED':
                    ActivityLog.objects.log_payment_activity(
                        transaction=instance,
                        activity_type='PAYMENT_CANCELLED',
                        description=f"Payment cancelled: KES {instance.amount}",
                        metadata={'reason': 'User cancelled'},
                        level='INFO'
                    )

                    # Send cancellation notification
                    try:
                        send_notification(
                            client=instance.client,
                            notification_type='PAYMENT_CANCELLED',
                            title='Payment Cancelled',
                            message=f'Payment of KES {instance.amount} was cancelled',
                            reference_id=str(instance.transaction_id),
                            metadata={
                                'amount': str(instance.amount),
                                'phone_number': instance.phone_number,
                                'transaction_id': str(instance.transaction_id)
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to send payment cancellation notification: {e}")

                elif instance.status == 'TIMEOUT':
                    ActivityLog.objects.log_payment_activity(
                        transaction=instance,
                        activity_type='PAYMENT_TIMEOUT',
                        description=f"Payment timeout: KES {instance.amount}",
                        metadata={'timeout_reason': 'User did not complete payment'},
                        level='WARNING'
                    )

                elif instance.status == 'PROCESSING':
                    ActivityLog.objects.log_payment_activity(
                        transaction=instance,
                        activity_type='PAYMENT_PROCESSING',
                        description=f"Payment processing: KES {instance.amount}",
                        metadata={'status': 'processing'}
                    )

    except Exception as e:
        logger.error(f"Error in transaction save signal: {e}")


@receiver(pre_save, sender=Transaction)
def store_original_transaction_status(sender, instance, **kwargs):
    """Store original transaction status before save."""
    try:
        if instance.pk:
            try:
                original = Transaction.objects.get(pk=instance.pk)
                instance._original_status = original.status
            except Transaction.DoesNotExist:
                instance._original_status = None
    except Exception as e:
        logger.error(f"Error storing original transaction status: {e}")


# Callback Signals
@receiver(post_save, sender=CallbackLog)
def track_callback_activity(sender, instance, created, **kwargs):
    """Track callback activities."""
    try:
        if created:
            ActivityLog.objects.log_system_activity(
                activity_type='CALLBACK_RECEIVED',
                description=f"Callback received: {instance.callback_type}",
                metadata={
                    'callback_type': instance.callback_type,
                    'ip_address': str(instance.ip_address),
                    'processed': instance.processed_successfully
                },
                ip_address=str(instance.ip_address)
            )

            if instance.processed_successfully:
                ActivityLog.objects.log_system_activity(
                    activity_type='CALLBACK_PROCESSED',
                    description=f"Callback processed successfully: {instance.callback_type}",
                    metadata={'callback_id': str(instance.log_id)}
                )
            else:
                ActivityLog.objects.log_system_activity(
                    activity_type='CALLBACK_FAILED',
                    description=f"Callback processing failed: {instance.callback_type}",
                    metadata={
                        'callback_id': str(instance.log_id),
                        'error': instance.error_message
                    },
                    level='ERROR',
                    error_message=instance.error_message
                )
    except Exception as e:
        logger.error(f"Error in callback activity signal: {e}")


# Configuration Signals
@receiver(post_save, sender=ClientEnvironmentVariable)
def track_env_var_changes(sender, instance, created, **kwargs):
    """Track environment variable changes."""
    try:
        action = 'created' if created else 'updated'
        ActivityLog.objects.log_client_activity(
            client=instance.client,
            activity_type='ENV_VAR_UPDATED',
            description=f"Environment variable {action}: {instance.get_variable_name()}",
            metadata={
                'variable_type': instance.variable_type,
                'variable_name': instance.get_variable_name(),
                'is_active': instance.is_active,
                'action': action
            }
        )
    except Exception as e:
        logger.error(f"Error in env var signal: {e}")


@receiver(post_save, sender=MpesaCredentials)
def track_mpesa_credentials_changes(sender, instance, created, **kwargs):
    """Track MPesa credentials changes."""
    try:
        action = 'created' if created else 'updated'
        ActivityLog.objects.log_client_activity(
            client=instance.client,
            activity_type='CREDENTIALS_UPDATED',
            description=f"MPesa credentials {action}: {instance.name}",
            metadata={
                'credentials_name': instance.name,
                'environment': instance.environment,
                'is_active': instance.is_active,
                'action': action
            }
        )

        # Send notification about credentials update
        try:
            from core.utils.notification_service import notify_credentials_updated
            notify_credentials_updated(instance.client, f"MPesa {instance.environment}")
        except Exception as e:
            logger.error(f"Failed to send credentials update notification: {e}")

    except Exception as e:
        logger.error(f"Error in MPesa credentials signal: {e}")


# Authentication Signals
@receiver(user_logged_in)
def track_user_login(sender, request, user, **kwargs):
    """Track user login."""
    try:
        ip_address = None
        user_agent = ''

        if request:
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')

        ActivityLog.objects.log_activity(
            activity_type='AUTH_SUCCESS',
            description=f"User logged in: {user.username}",
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={'username': user.username}
        )
    except Exception as e:
        logger.error(f"Error in user login signal: {e}")


@receiver(user_logged_out)
def track_user_logout(sender, request, user, **kwargs):
    """Track user logout."""
    try:
        ip_address = None

        if request:
            ip_address = request.META.get('REMOTE_ADDR')

        ActivityLog.objects.log_activity(
            activity_type='CLIENT_LOGOUT',
            description=f"User logged out: {user.username if user else 'Unknown'}",
            user=user,
            ip_address=ip_address,
            metadata={'username': user.username if user else 'Unknown'}
        )
    except Exception as e:
        logger.error(f"Error in user logout signal: {e}")


@receiver(user_login_failed)
def track_user_login_failed(sender, credentials, request, **kwargs):
    """Track failed login attempts."""
    try:
        ip_address = None
        user_agent = ''

        if request:
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')

        username = credentials.get('username', 'Unknown')

        ActivityLog.objects.log_activity(
            activity_type='AUTH_FAILED',
            description=f"Failed login attempt for: {username}",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                'username': username,
                'credentials_provided': bool(credentials)
            },
            level='WARNING'
        )
    except Exception as e:
        logger.error(f"Error in user login failed signal: {e}")


# Notification Signals
@receiver(post_save, sender=Notification)
def track_notification_activity(sender, instance, created, **kwargs):
    """Track notification creation and updates."""
    try:
        if created:
            ActivityLog.objects.log_client_activity(
                client=instance.client,
                activity_type='NOTIFICATION_SENT',
                description=f"Notification created: {instance.title}",
                metadata={
                    'notification_type': instance.notification_type,
                    'title': instance.title,
                    'channels': instance.channels_sent,
                    'status': instance.status
                }
            )
        else:
            # Check for status changes
            if instance.status == 'FAILED':
                ActivityLog.objects.log_client_activity(
                    client=instance.client,
                    activity_type='NOTIFICATION_FAILED',
                    description=f"Notification failed: {instance.title}",
                    metadata={
                        'notification_type': instance.notification_type,
                        'error': instance.error_message,
                        'retry_count': instance.retry_count
                    },
                    level='WARNING',
                    error_message=instance.error_message
                )
    except Exception as e:
        logger.error(f"Error in notification signal: {e}")


# Generic model tracking for other important models
def create_generic_model_signals():
    """Create generic signals for tracking CRUD operations on all models."""

    # List of models to track
    from django.apps import apps

    # Get all models from our apps
    our_apps = ['core', 'clients', 'mpesa']

    for app_name in our_apps:
        try:
            app = apps.get_app_config(app_name)
            for model in app.get_models():
                # Skip models we already have specific signals for
                if model.__name__ in ['ActivityLog', 'Client', 'Transaction', 'CallbackLog',
                                    'ClientEnvironmentVariable', 'MpesaCredentials', 'Notification']:
                    continue

                # Create post_save signal
                @receiver(post_save, sender=model)
                def track_generic_model_save(sender, instance, created, **kwargs):
                    try:
                        action = 'created' if created else 'updated'
                        model_name = sender.__name__

                        # Try to get associated client
                        client = None
                        if hasattr(instance, 'client'):
                            client = instance.client
                        elif hasattr(instance, 'client_id'):
                            try:
                                from clients.models import Client
                                client = Client.objects.get(pk=instance.client_id)
                            except:
                                pass

                        ActivityLog.objects.log_activity(
                            activity_type='MODEL_CREATED' if created else 'MODEL_UPDATED',
                            description=f"{model_name} {action}: {str(instance)}",
                            client=client,
                            metadata={
                                'model': model_name,
                                'action': action,
                                'instance_id': str(getattr(instance, 'pk', 'unknown')),
                                'instance_data': safe_model_to_dict(instance)
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error in generic model save signal for {sender.__name__}: {e}")

                # Create post_delete signal
                @receiver(post_delete, sender=model)
                def track_generic_model_delete(sender, instance, **kwargs):
                    try:
                        model_name = sender.__name__

                        # Try to get associated client
                        client = None
                        if hasattr(instance, 'client'):
                            client = instance.client

                        ActivityLog.objects.log_activity(
                            activity_type='MODEL_DELETED',
                            description=f"{model_name} deleted: {str(instance)}",
                            client=client,
                            metadata={
                                'model': model_name,
                                'action': 'deleted',
                                'instance_id': str(getattr(instance, 'pk', 'unknown')),
                                'instance_data': safe_model_to_dict(instance)
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error in generic model delete signal for {sender.__name__}: {e}")

        except Exception as e:
            logger.error(f"Error setting up signals for app {app_name}: {e}")


# Initialize generic model signals
# create_generic_model_signals()  # Commented out to avoid duplicate signal registration
