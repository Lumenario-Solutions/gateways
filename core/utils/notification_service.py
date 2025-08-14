"""
Notification service for sending notifications via multiple channels using client-specific settings.
"""

import os
from typing import Dict, Any, Optional
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.template import Template, Context
from .send_mail import send_email
from .send_message import send_message
import logging

logger = logging.getLogger(__name__)


def get_client_env_variable(client, variable_type, default_value=None):
    """
    Get environment variable for a specific client or fallback to default.

    Args:
        client: Client instance
        variable_type: Type of environment variable
        default_value: Default value if not found

    Returns:
        str: Environment variable value
    """
    try:
        from core.models import ClientEnvironmentVariable

        env_var = ClientEnvironmentVariable.objects.get_variable(client, variable_type)
        if env_var:
            decrypted_value = env_var.get_decrypted_value()
            if decrypted_value:
                return decrypted_value
    except Exception as e:
        logger.warning(f"Could not get client env variable {variable_type} for {client.name}: {e}")

    # Fallback to default environment variables
    if variable_type == 'RESEND_API_KEY':
        return getattr(settings, 'RESEND_API_KEY', None) or os.getenv('RESEND_API_KEY') or default_value
    elif variable_type == 'MESSAGE_API_URL':
        return getattr(settings, 'MESSAGE_API_URL', None) or os.getenv('API_URL') or default_value
    elif variable_type == 'MESSAGE_API_KEY':
        return getattr(settings, 'MESSAGE_API_KEY', None) or os.getenv('API_KEY') or default_value

    return default_value


def create_email_template(notification_type, data):
    """
    Create email template for notification.

    Args:
        notification_type: Type of notification
        data: Data for template

    Returns:
        tuple: (subject, html_content)
    """
    base_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{{ title }}</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f4f4f4;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(0,0,0,0.1);
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #e9ecef;
                padding-bottom: 20px;
            }
            .logo {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 10px;
            }
            .title {
                color: #27ae60;
                font-size: 20px;
                margin: 20px 0;
            }
            .content {
                margin: 20px 0;
            }
            .highlight {
                background-color: #e8f5e8;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #27ae60;
                margin: 15px 0;
            }
            .footer {
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e9ecef;
                text-align: center;
                color: #6c757d;
                font-size: 12px;
            }
            .timestamp {
                color: #6c757d;
                font-size: 12px;
                text-align: right;
                margin-top: 15px;
            }
            .client-tag {
                background-color: #f8f9fa;
                color: #495057;
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 11px;
                display: inline-block;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">Payment Gateway</div>
                <h1 class="title">{{ title }}</h1>
            </div>

            <div class="content">
                {{ content|safe }}
            </div>

            {% if highlight_info %}
            <div class="highlight">
                {{ highlight_info|safe }}
            </div>
            {% endif %}

            <div class="timestamp">
                {{ timestamp }}
            </div>

            <div class="footer">
                <p>This is an automated notification from your Payment Gateway system.</p>
                <div class="client-tag">{{ client_hashtag }}</div>
            </div>
        </div>
    </body>
    </html>
    """

    # Prepare template data
    template_data = {
        'title': data.get('title', 'Notification'),
        'content': data.get('message', ''),
        'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'client_hashtag': data.get('client_hashtag', ''),
        'highlight_info': data.get('highlight_info', ''),
    }

    # Render template
    template = Template(base_template)
    html_content = template.render(Context(template_data))

    subject = f"Payment Gateway - {data.get('title', 'Notification')}"

    return subject, html_content


def create_whatsapp_message(notification_type, data):
    """
    Create WhatsApp message for notification.

    Args:
        notification_type: Type of notification
        data: Data for message

    Returns:
        str: Formatted WhatsApp message
    """
    timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    client_hashtag = data.get('client_hashtag', '')

    # Professional WhatsApp message template
    message_parts = [
        "🔔 *Payment Gateway Notification*",
        "",
        f"*{data.get('title', 'Notification')}*",
        "",
        data.get('message', ''),
        "",
    ]

    # Add highlight information if available
    if data.get('highlight_info'):
        message_parts.extend([
            "📋 *Details:*",
            data.get('highlight_info'),
            "",
        ])

    # Add metadata if available
    metadata = data.get('metadata', {})
    if metadata:
        message_parts.append("📊 *Summary:*")
        for key, value in metadata.items():
            if key not in ['client_id', 'notification_id']:
                formatted_key = key.replace('_', ' ').title()
                message_parts.append(f"• {formatted_key}: {value}")
        message_parts.append("")

    # Add timestamp and client tag
    message_parts.extend([
        f"⏰ {timestamp}",
        "",
        f"Client: {client_hashtag}"
    ])

    return "\n".join(message_parts)


def send_notification(client, notification_type, title, message,
                     reference_id=None, metadata=None, channels=None):
    """
    Send notification to client via multiple channels.

    Args:
        client: Client instance
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        reference_id: Reference ID (optional)
        metadata: Additional metadata (optional)
        channels: List of channels to send to (optional, defaults to ['EMAIL', 'WHATSAPP'])

    Returns:
        dict: Results of notification sending
    """
    try:
        from core.models import Notification

        # Default channels
        if channels is None:
            channels = ['EMAIL', 'WHATSAPP']

        # Create notification record
        notification = Notification.objects.create_notification(
            client=client,
            notification_type=notification_type,
            title=title,
            message=message,
            reference_id=reference_id,
            metadata=metadata or {}
        )

        results = {
            'notification_id': str(notification.id),
            'channels': {},
            'success': False,
            'errors': []
        }

        # Prepare data for templates
        template_data = {
            'title': title,
            'message': message,
            'client_hashtag': notification.get_client_hashtag(),
            'metadata': metadata or {},
            'highlight_info': metadata.get('highlight_info', '') if metadata else ''
        }

        # Send via email
        if 'EMAIL' in channels:
            try:
                # Get client-specific email settings
                api_key = get_client_env_variable(client, 'RESEND_API_KEY')

                if api_key:
                    subject, html_content = create_email_template(notification_type, template_data)

                    # Use client-specific email function
                    email_result = send_email_with_client_settings(
                        to=client.email,
                        subject=subject,
                        content=html_content,
                        api_key=api_key
                    )

                    if email_result.get('success'):
                        notification.mark_channel_sent('EMAIL', success=True)
                        results['channels']['EMAIL'] = {'success': True, 'data': email_result}
                    else:
                        notification.mark_channel_sent('EMAIL', success=False, error_message=email_result.get('error'))
                        results['channels']['EMAIL'] = {'success': False, 'error': email_result.get('error')}
                else:
                    error_msg = "No email API key configured for client"
                    results['channels']['EMAIL'] = {'success': False, 'error': error_msg}
                    results['errors'].append(error_msg)

            except Exception as e:
                error_msg = f"Email sending failed: {str(e)}"
                notification.mark_channel_sent('EMAIL', success=False, error_message=error_msg)
                results['channels']['EMAIL'] = {'success': False, 'error': error_msg}
                results['errors'].append(error_msg)
                logger.error(error_msg)

        # Send via WhatsApp
        if 'WHATSAPP' in channels:
            try:
                # Get client-specific WhatsApp settings
                api_url = get_client_env_variable(client, 'MESSAGE_API_URL')
                api_key = get_client_env_variable(client, 'MESSAGE_API_KEY')

                if api_url and api_key:
                    whatsapp_message = create_whatsapp_message(notification_type, template_data)

                    # Use client-specific message function
                    whatsapp_result = send_message(
                        to=client.phone_number if hasattr(client, 'phone_number') else '',
                        conversation=whatsapp_message,
                        client=client,
                        api_url=api_url,
                    )

                    if whatsapp_result.get('success'):
                        notification.mark_channel_sent('WHATSAPP', success=True)
                        results['channels']['WHATSAPP'] = {'success': True, 'data': whatsapp_result}
                    else:
                        notification.mark_channel_sent('WHATSAPP', success=False, error_message=whatsapp_result.get('error'))
                        results['channels']['WHATSAPP'] = {'success': False, 'error': whatsapp_result.get('error')}
                else:
                    error_msg = "No WhatsApp API configuration for client"
                    results['channels']['WHATSAPP'] = {'success': False, 'error': error_msg}
                    results['errors'].append(error_msg)

            except Exception as e:
                error_msg = f"WhatsApp sending failed: {str(e)}"
                notification.mark_channel_sent('WHATSAPP', success=False, error_message=error_msg)
                results['channels']['WHATSAPP'] = {'success': False, 'error': error_msg}
                results['errors'].append(error_msg)
                logger.error(error_msg)

        # Check if any channel succeeded
        results['success'] = any(
            channel_result.get('success', False)
            for channel_result in results['channels'].values()
        )

        logger.info(f"Notification sent for client {client.name}: {notification.id}")
        return results

    except Exception as e:
        error_msg = f"Failed to send notification: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'channels': {},
            'errors': [error_msg]
        }


def send_email_with_client_settings(to, subject, content, api_key, from_email=None, reply_to=None):
    """
    Send email using client-specific API key.
    """
    import requests
    import json

    # Set default values
    if from_email is None:
        from_email = "Payment Gateway <noreply@lmn.co.ke>"
    if reply_to is None:
        reply_to = "support@lmn.co.ke"

    # Ensure 'to' is a list
    if isinstance(to, str):
        to = [to]

    # Prepare payload for Resend API
    payload = {
        "from": from_email,
        "to": to,
        "subject": subject,
        "html": content,
        "reply_to": reply_to
    }

    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Resend API endpoint
    api_url = "https://api.resend.com/emails"

    try:
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )

        try:
            api_response_data = response.json()
        except json.JSONDecodeError:
            api_response_data = {"raw_response": response.text}

        if response.status_code >= 200 and response.status_code < 300:
            return {
                "success": True,
                "message": f"Email sent successfully. ID: {api_response_data.get('id', 'unknown')}",
                "data": api_response_data
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "data": api_response_data
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Convenience functions for common notification types
def notify_client_created(client):
    """Send notification when client is created."""
    return send_notification(
        client=client,
        notification_type='CLIENT_CREATED',
        title='Welcome to Payment Gateway',
        message=f'Your account has been successfully created. You can now start integrating with our payment services.',
        metadata={
            'client_id': str(client.client_id),
            'api_key': client.api_key,
            'highlight_info': f'Your API Key: {client.api_key}<br>Please keep this secure and do not share it.'
        }
    )


def notify_payment_received(client, transaction):
    """Send notification when payment is received."""
    return send_notification(
        client=client,
        notification_type='PAYMENT_RECEIVED',
        title='Payment Received',
        message=f'Payment of KES {transaction.amount} has been successfully received.',
        reference_id=str(transaction.transaction_id),
        metadata={
            'amount': str(transaction.amount),
            'phone_number': transaction.phone_number,
            'receipt_number': transaction.mpesa_receipt_number or 'N/A',
            'transaction_id': str(transaction.transaction_id),
            'highlight_info': f'Amount: KES {transaction.amount}<br>From: {transaction.phone_number}<br>Receipt: {transaction.mpesa_receipt_number or "N/A"}'
        }
    )


def notify_payment_failed(client, transaction):
    """Send notification when payment fails."""
    return send_notification(
        client=client,
        notification_type='PAYMENT_FAILED',
        title='Payment Failed',
        message=f'Payment of KES {transaction.amount} failed. Reason: {transaction.response_description}',
        reference_id=str(transaction.transaction_id),
        metadata={
            'amount': str(transaction.amount),
            'phone_number': transaction.phone_number,
            'transaction_id': str(transaction.transaction_id),
            'error_reason': transaction.response_description,
            'highlight_info': f'Amount: KES {transaction.amount}<br>From: {transaction.phone_number}<br>Reason: {transaction.response_description}'
        }
    )


def notify_credentials_updated(client, credential_type):
    """Send notification when credentials are updated."""
    return send_notification(
        client=client,
        notification_type='MPESA_CREDENTIALS_UPDATED',
        title='Credentials Updated',
        message=f'Your {credential_type} credentials have been successfully updated.',
        metadata={
            'credential_type': credential_type,
            'updated_at': timezone.now().isoformat(),
            'highlight_info': f'Credential Type: {credential_type}<br>Updated on: {timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")}'
        }
    )
