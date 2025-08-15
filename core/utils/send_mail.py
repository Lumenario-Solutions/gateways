import os
import json
import requests
from django.conf import settings
from typing import Dict, Any, List, Union
import logging
import time
import traceback

logger = logging.getLogger(__name__)

def log_email_activity(activity_type, description, client=None, metadata=None, level='INFO', error_message=None):
    """Log email-related activity to ActivityLog."""
    try:
        from core.models import ActivityLog
        
        # Add error_message to metadata instead of passing as separate parameter
        if error_message and metadata:
            metadata['error_message'] = error_message
        elif error_message:
            metadata = {'error_message': error_message}
        
        ActivityLog.objects.log_activity(
            activity_type=activity_type,
            description=description,
            client=client,
            metadata=metadata or {},
            level=level
        )
    except Exception as e:
        logger.error(f"Failed to log email activity: {e}")

def send_email(to: Union[str, List[str]], subject: str, content: str,
               from_email: str = None, reply_to: str = None, client=None) -> Dict[str, Any]:
    """
    Send an email using Resend API with comprehensive logging and error tracking.

    Args:
        to (str or List[str]): Recipient email address(es)
        subject (str): Email subject
        content (str): HTML content of the email
        from_email (str, optional): Sender email. Defaults to "Lumenario <noreply@lmn.co.ke>"
        reply_to (str, optional): Reply-to email. Defaults to "support@lmn.co.ke"
        client (Client, optional): Client instance for client-specific settings

    Returns:
        Dict[str, Any]: Structured response with success boolean and additional data
        {
            "success": bool,
            "message": str,
            "data": dict or None,
            "error": str or None,
            "email_id": str or None,
            "duration_ms": int
        }
    """
    start_time = time.time()

    # Initialize response structure
    response_data = {
        "success": False,
        "message": "",
        "data": None,
        "error": None,
        "email_id": None,
        "duration_ms": 0
    }

    # Validate inputs
    if not to:
        error_msg = "Recipient email address is required"
        response_data.update({
            "message": error_msg,
            "error": "INVALID_RECIPIENT"
        })
        log_email_activity(
            'EMAIL_FAILED',
            error_msg,
            client=client,
            metadata={'reason': 'invalid_recipient'},
            level='ERROR',
            error_message=error_msg
        )
        return response_data

    if not subject or not content:
        error_msg = "Subject and content are required"
        response_data.update({
            "message": error_msg,
            "error": "MISSING_CONTENT"
        })
        log_email_activity(
            'EMAIL_FAILED',
            error_msg,
            client=client,
            metadata={'reason': 'missing_content'},
            level='ERROR',
            error_message=error_msg
        )
        return response_data

    # Get API key - try client-specific first, then fallback to global
    api_key = None
    api_key_source = "global"

    if client:
        try:
            from core.models import ClientEnvironmentVariable
            env_var = ClientEnvironmentVariable.objects.get_variable(client, 'RESEND_API_KEY')
            if env_var:
                api_key = env_var.get_decrypted_value()
                api_key_source = "client_specific"
                logger.info(f"Using client-specific email API key for {client.name}")
        except Exception as e:
            logger.warning(f"Could not get client-specific email API key for {client.name}: {e}")
            log_email_activity(
                'EMAIL_FAILED',
                f"Failed to retrieve client-specific API key: {str(e)}",
                client=client,
                metadata={'reason': 'api_key_retrieval_failed'},
                level='WARNING',
                error_message=str(e)
            )

    # Fallback to global settings
    if not api_key:
        api_key = getattr(settings, 'RESEND_API_KEY', None) or os.getenv('RESEND_API_KEY')
        if api_key:
            api_key_source = "global"

    if not api_key:
        error_msg = "Missing Resend API key"
        response_data.update({
            "message": error_msg,
            "error": "Set RESEND_API_KEY in settings or environment variables"
        })
        log_email_activity(
            'EMAIL_FAILED',
            error_msg,
            client=client,
            metadata={'reason': 'missing_api_key', 'api_key_source': api_key_source},
            level='ERROR',
            error_message=error_msg
        )
        return response_data

    # Set default values
    if from_email is None:
        from_email = "Lumenario <noreply@lmn.co.ke>"
    if reply_to is None:
        reply_to = "support@lmn.co.ke"

    # Ensure 'to' is a list
    if isinstance(to, str):
        to = [to]

    # Validate email addresses
    import re
    email_regex = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    invalid_emails = [email for email in to if not email_regex.match(email)]

    if invalid_emails:
        error_msg = f"Invalid email addresses: {', '.join(invalid_emails)}"
        response_data.update({
            "message": error_msg,
            "error": "INVALID_EMAIL_FORMAT"
        })
        log_email_activity(
            'EMAIL_FAILED',
            error_msg,
            client=client,
            metadata={'invalid_emails': invalid_emails, 'reason': 'invalid_email_format'},
            level='ERROR',
            error_message=error_msg
        )
        return response_data

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

    # Log email sending attempt
    log_email_activity(
        'EMAIL_SENDING',
        f"Attempting to send email to {', '.join(to)}",
        client=client,
        metadata={
            'subject': subject,
            'recipients': to,
            'from_email': from_email,
            'api_key_source': api_key_source,
            'content_length': len(content)
        }
    )

    try:
        # Send POST request to Resend API
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms

        # Try to parse JSON response
        try:
            api_response_data = response.json()
        except json.JSONDecodeError:
            api_response_data = {"raw_response": response.text}

        # Check if request was successful (status code 2xx)
        if response.status_code >= 200 and response.status_code < 300:
            email_id = api_response_data.get('id', 'unknown')
            response_data.update({
                "success": True,
                "message": f"Email sent successfully. ID: {email_id}",
                "data": api_response_data,
                "email_id": email_id
            })

            # Log successful email sending
            log_email_activity(
                'EMAIL_SENT',
                f"Email sent successfully to {', '.join(to)}",
                client=client,
                metadata={
                    'email_id': email_id,
                    'subject': subject,
                    'recipients': to,
                    'duration_ms': duration_ms,
                    'api_response': api_response_data
                }
            )

            logger.info(f"Email sent successfully to {to}. ID: {email_id}, Duration: {duration_ms}ms")
            print(f"Email sent successfully. ID: {email_id}")  # Keep original behavior

        else:
            error_message = api_response_data.get('message', f'HTTP {response.status_code}')
            error_details = f"HTTP {response.status_code}: {response.text}"

            response_data.update({
                "message": f"Failed to send email: {error_message}",
                "error": error_details,
                "data": api_response_data
            })

            # Log email failure
            log_email_activity(
                'EMAIL_FAILED',
                f"Failed to send email to {', '.join(to)}",
                client=client,
                metadata={
                    'subject': subject,
                    'recipients': to,
                    'status_code': response.status_code,
                    'error_message': error_message,
                    'duration_ms': duration_ms,
                    'api_response': api_response_data
                },
                level='ERROR',
                error_message=error_details
            )

            logger.error(f"Failed to send email to {to}. Status: {response.status_code}, Response: {response.text}")

    except requests.exceptions.Timeout:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = "Request timeout - The email request took too long to complete"

        response_data.update({
            "message": "Request timeout",
            "error": error_msg
        })

        log_email_activity(
            'EMAIL_FAILED',
            f"Email timeout to {', '.join(to)}",
            client=client,
            metadata={
                'subject': subject,
                'recipients': to,
                'duration_ms': duration_ms,
                'reason': 'timeout'
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Timeout error sending email to {to}")

    except requests.exceptions.ConnectionError:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = "Connection error - Unable to connect to Resend API"

        response_data.update({
            "message": "Connection error",
            "error": error_msg
        })

        log_email_activity(
            'EMAIL_FAILED',
            f"Email connection error to {', '.join(to)}",
            client=client,
            metadata={
                'subject': subject,
                'recipients': to,
                'duration_ms': duration_ms,
                'reason': 'connection_error'
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Connection error sending email to {to}")

    except requests.exceptions.RequestException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = f"Request failed: {str(e)}"

        response_data.update({
            "message": "Request failed",
            "error": error_msg
        })

        log_email_activity(
            'EMAIL_FAILED',
            f"Email request failed to {', '.join(to)}",
            client=client,
            metadata={
                'subject': subject,
                'recipients': to,
                'duration_ms': duration_ms,
                'reason': 'request_exception',
                'exception_type': type(e).__name__
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Request error sending email to {to}: {str(e)}")

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = f"Unexpected error occurred: {str(e)}"
        stack_trace = traceback.format_exc()

        response_data.update({
            "message": "Unexpected error occurred",
            "error": error_msg
        })

        log_email_activity(
            'EMAIL_FAILED',
            f"Unexpected email error to {', '.join(to)}",
            client=client,
            metadata={
                'subject': subject,
                'recipients': to,
                'duration_ms': duration_ms,
                'reason': 'unexpected_error',
                'exception_type': type(e).__name__,
                'stack_trace': stack_trace
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Unexpected error sending email to {to}: {str(e)}")

    return response_data


def send_text_email(to: Union[str, List[str]], subject: str, text_content: str,
                   from_email: str = None, reply_to: str = None, client=None) -> Dict[str, Any]:
    """
    Send a plain text email using Resend API with comprehensive logging.

    Args:
        to (str or List[str]): Recipient email address(es)
        subject (str): Email subject
        text_content (str): Plain text content of the email
        from_email (str, optional): Sender email. Defaults to "Lumenario <noreply@lmn.co.ke>"
        reply_to (str, optional): Reply-to email. Defaults to "support@lmn.co.ke"
        client (Client, optional): Client instance for logging

    Returns:
        Dict[str, Any]: Structured response with success boolean and additional data
    """
    start_time = time.time()

    # Initialize response structure
    response_data = {
        "success": False,
        "message": "",
        "data": None,
        "error": None,
        "email_id": None,
        "duration_ms": 0
    }

    # Get API key from Django settings or environment variables
    api_key = getattr(settings, 'RESEND_API_KEY', None) or os.getenv('RESEND_API_KEY')

    if not api_key:
        error_msg = "Missing Resend API key"
        response_data.update({
            "message": error_msg,
            "error": "Set RESEND_API_KEY in settings or environment variables"
        })
        log_email_activity(
            'EMAIL_FAILED',
            error_msg,
            client=client,
            metadata={'reason': 'missing_api_key', 'email_type': 'text'},
            level='ERROR',
            error_message=error_msg
        )
        return response_data

    # Set default values
    if from_email is None:
        from_email = "Lumenario <noreply@lmn.co.ke>"
    if reply_to is None:
        reply_to = "support@lmn.co.ke"

    # Ensure 'to' is a list
    if isinstance(to, str):
        to = [to]

    # Prepare payload for Resend API (using text instead of html)
    payload = {
        "from": from_email,
        "to": to,
        "subject": subject,
        "text": text_content,
        "reply_to": reply_to
    }

    # Prepare headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Resend API endpoint
    api_url = "https://api.resend.com/emails"

    # Log email sending attempt
    log_email_activity(
        'EMAIL_SENDING',
        f"Attempting to send text email to {', '.join(to)}",
        client=client,
        metadata={
            'subject': subject,
            'recipients': to,
            'from_email': from_email,
            'email_type': 'text',
            'content_length': len(text_content)
        }
    )

    try:
        # Send POST request to Resend API
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms

        # Try to parse JSON response
        try:
            api_response_data = response.json()
        except json.JSONDecodeError:
            api_response_data = {"raw_response": response.text}

        # Check if request was successful (status code 2xx)
        if response.status_code >= 200 and response.status_code < 300:
            email_id = api_response_data.get('id', 'unknown')
            response_data.update({
                "success": True,
                "message": f"Email sent successfully. ID: {email_id}",
                "data": api_response_data,
                "email_id": email_id
            })

            # Log successful email sending
            log_email_activity(
                'EMAIL_SENT',
                f"Text email sent successfully to {', '.join(to)}",
                client=client,
                metadata={
                    'email_id': email_id,
                    'subject': subject,
                    'recipients': to,
                    'email_type': 'text',
                    'duration_ms': duration_ms,
                    'api_response': api_response_data
                }
            )

            logger.info(f"Text email sent successfully to {to}. ID: {email_id}")
            print(f"Email sent successfully. ID: {email_id}")

        else:
            error_message = api_response_data.get('message', f'HTTP {response.status_code}')
            error_details = f"HTTP {response.status_code}: {response.text}"

            response_data.update({
                "message": f"Failed to send email: {error_message}",
                "error": error_details,
                "data": api_response_data
            })

            # Log email failure
            log_email_activity(
                'EMAIL_FAILED',
                f"Failed to send text email to {', '.join(to)}",
                client=client,
                metadata={
                    'subject': subject,
                    'recipients': to,
                    'email_type': 'text',
                    'status_code': response.status_code,
                    'error_message': error_message,
                    'duration_ms': duration_ms
                },
                level='ERROR',
                error_message=error_details
            )

            logger.error(f"Failed to send text email to {to}. Status: {response.status_code}")

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = f"Unexpected error occurred: {str(e)}"

        response_data.update({
            "message": "Unexpected error occurred",
            "error": error_msg
        })

        log_email_activity(
            'EMAIL_FAILED',
            f"Unexpected error sending text email to {', '.join(to)}",
            client=client,
            metadata={
                'subject': subject,
                'recipients': to,
                'email_type': 'text',
                'duration_ms': duration_ms,
                'reason': 'unexpected_error',
                'exception_type': type(e).__name__
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Unexpected error sending text email to {to}: {str(e)}")

    return response_data