import os
import json
import requests
from django.conf import settings
from typing import Dict, Any
import logging
import time
import traceback
import urllib.parse

logger = logging.getLogger(__name__)

def log_message_activity(activity_type, description, client=None, metadata=None, level='INFO', error_message=None):
    """Log message-related activity to ActivityLog."""
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
        logger.error(f"Failed to log message activity: {e}")

def send_message(to: str, conversation: str, client=None) -> Dict[str, Any]:
    """
    Send a message using HTTP bypass to avoid PythonAnywhere firewall restrictions.
    """
    start_time = time.time()

    response_data = {
        "success": False,
        "message": "",
        "data": None,
        "error": None,
        "message_id": None,
        "duration_ms": 0
    }

    # Validate inputs
    if not to:
        error_msg = "Recipient identifier is required"
        response_data.update({
            "message": error_msg,
            "error": "INVALID_RECIPIENT"
        })
        return response_data

    if not conversation:
        error_msg = "Message content is required"
        response_data.update({
            "message": error_msg,
            "error": "MISSING_CONTENT"
        })
        return response_data

    # Get API credentials - try client-specific first, then fallback to global
    api_url = None
    api_key = None
    api_source = "global"

    if client:
        try:
            from core.models import ClientEnvironmentVariable

            # Try to get client-specific URL
            url_var = ClientEnvironmentVariable.objects.get_variable(client, 'MESSAGE_API_URL')
            if url_var:
                api_url = url_var.get_decrypted_value()
                api_source = "client_specific"

            # Try to get client-specific API key
            key_var = ClientEnvironmentVariable.objects.get_variable(client, 'MESSAGE_API_KEY')
            if key_var:
                api_key = key_var.get_decrypted_value()

            if api_url and api_key:
                logger.info(f"Using client-specific message API settings for {client.name}")

        except Exception as e:
            logger.warning(f"Could not get client-specific message API settings for {client.name}: {e}")
            log_message_activity(
                'MESSAGE_FAILED',
                f"Failed to retrieve client-specific API settings: {str(e)}",
                client=client,
                metadata={'reason': 'api_settings_retrieval_failed'},
                level='WARNING',
                error_message=str(e)
            )

    # Fallback to global settings
    if not api_url:
        api_url = getattr(settings, 'MESSAGE_API_URL', None) or os.getenv('API_URL')
        api_source = "global"
    if not api_key:
        api_key = getattr(settings, 'MESSAGE_API_KEY', None) or os.getenv('API_KEY')

    # Log credential status for debugging
    logger.info(f"API credentials status - Source: {api_source}, "
                f"URL: {'✓' if api_url else '✗'} ({api_url[:50] + '...' if api_url and len(api_url) > 50 else api_url or 'None'}), "
                f"Key: {'✓' if api_key else '✗'} ({'***' + api_key[-4:] if api_key and len(api_key) > 4 else 'None'})")

    if not api_url or not api_key:
        error_msg = "Missing API credentials"
        error_details = "Set MESSAGE_API_URL and MESSAGE_API_KEY in settings or API_URL and API_KEY in environment variables"
        response_data.update({
            "message": error_msg,
            "error": error_details
        })
        log_message_activity(
            'MESSAGE_FAILED',
            error_msg,
            client=client,
            metadata={
                'reason': 'missing_api_credentials',
                'api_source': api_source,
                'has_url': bool(api_url),
                'has_key': bool(api_key),
                'api_url_preview': api_url[:50] + '...' if api_url and len(api_url) > 50 else api_url,
                'api_key_preview': '***' + api_key[-4:] if api_key and len(api_key) > 4 else None
            },
            level='ERROR',
            error_message=error_details
        )
        return response_data

    # Bypass firewall using api.lmn.co.ke
    encoded_url = urllib.parse.quote(api_url, safe='')
    bypass_url = f"https://api.lmn.co.ke/api/proxy?url={encoded_url}"

    payload = {
        "to": to,
        "conversation": conversation
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Validate phone number format (basic validation)
    if to.startswith('254') and len(to) not in [12, 13]:
        logger.warning(f"Potentially invalid phone number format: {to}")

    # Validate message length
    if len(conversation) > 1000:  # Typical SMS limit
        logger.warning(f"Message length ({len(conversation)}) exceeds typical SMS limit")

    # Log message sending attempt with credential info
    logger.info(f"Attempting to send message to {to} using {api_source} credentials via bypass")
    log_message_activity(
        'MESSAGE_SENDING',
        f"Attempting to send message to {to}",
        client=client,
        metadata={
            'recipient': to,
            'message_length': len(conversation),
            'api_source': api_source,
            'api_url_preview': api_url[:50] + '...' if len(api_url) > 50 else api_url,
            'api_key_preview': '***' + api_key[-4:] if api_key and len(api_key) > 4 else 'None',
            'has_credentials': bool(api_url and api_key),
            'bypass_method': 'allorigins'
        }
    )

    try:
        # Send POST request via bypass
        response = requests.post(
            bypass_url,
            json=payload,
            headers=headers,
            timeout=30
        )

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms

        # Try to parse JSON response, fallback to text
        try:
            api_response_data = response.json()
        except json.JSONDecodeError:
            api_response_data = {"raw_response": response.text}

        # Check if request was successful (status code 2xx)
        if response.status_code >= 200 and response.status_code < 300:
            # Try to extract message ID from response
            message_id = None
            if isinstance(api_response_data, dict):
                message_id = api_response_data.get('id') or api_response_data.get('message_id') or api_response_data.get('messageId')

            response_data.update({
                "success": True,
                "message": "Message sent successfully",
                "data": api_response_data,
                "message_id": message_id
            })

            # Log successful message sending
            log_message_activity(
                'MESSAGE_SENT',
                f"Message sent successfully to {to}",
                client=client,
                metadata={
                    'recipient': to,
                    'message_id': message_id,
                    'message_length': len(conversation),
                    'duration_ms': duration_ms,
                    'status_code': response.status_code,
                    'api_response': api_response_data,
                    'bypass_method': 'allorigins'
                }
            )

            logger.info(f"Message sent successfully to {to}. Status: {response.status_code}, Duration: {duration_ms}ms")
            print(f"Success: {response.text}")  # Keep original behavior

        else:
            error_message = "API request failed"
            if isinstance(api_response_data, dict):
                error_message = api_response_data.get('message') or api_response_data.get('error') or error_message

            error_details = f"HTTP {response.status_code}: {response.text}"

            response_data.update({
                "message": f"API request failed with status {response.status_code}",
                "error": error_details,
                "data": api_response_data
            })

            # Log message failure
            log_message_activity(
                'MESSAGE_FAILED',
                f"Failed to send message to {to}",
                client=client,
                metadata={
                    'recipient': to,
                    'message_length': len(conversation),
                    'status_code': response.status_code,
                    'error_message': error_message,
                    'duration_ms': duration_ms,
                    'api_response': api_response_data,
                    'bypass_method': 'allorigins'
                },
                level='ERROR',
                error_message=error_details
            )

            logger.error(f"API request failed for {to}. Status: {response.status_code}, Response: {response.text}")

    except requests.exceptions.Timeout:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = "Request timeout - The message request took too long to complete"

        response_data.update({
            "message": "Request timeout",
            "error": error_msg
        })

        log_message_activity(
            'MESSAGE_FAILED',
            f"Message timeout to {to}",
            client=client,
            metadata={
                'recipient': to,
                'message_length': len(conversation),
                'duration_ms': duration_ms,
                'reason': 'timeout',
                'bypass_method': 'allorigins'
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Timeout error sending message to {to}")

    except requests.exceptions.ConnectionError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = f"Connection error - Unable to connect to the API endpoint: {str(e)}"

        response_data.update({
            "message": "Connection error",
            "error": error_msg
        })

        log_message_activity(
            'MESSAGE_FAILED',
            f"Message connection error to {to}",
            client=client,
            metadata={
                'recipient': to,
                'message_length': len(conversation),
                'duration_ms': duration_ms,
                'reason': 'connection_error',
                'api_url_preview': api_url[:50] + '...' if len(api_url) > 50 else api_url,
                'api_key_preview': '***' + api_key[-4:] if api_key and len(api_key) > 4 else 'None',
                'api_source': api_source,
                'connection_error_details': str(e),
                'bypass_method': 'allorigins'
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Connection error sending message to {to}. URL: {api_url}, Error: {str(e)}")

    except requests.exceptions.RequestException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = f"Request failed: {str(e)}"

        response_data.update({
            "message": "Request failed",
            "error": error_msg
        })

        log_message_activity(
            'MESSAGE_FAILED',
            f"Message request failed to {to}",
            client=client,
            metadata={
                'recipient': to,
                'message_length': len(conversation),
                'duration_ms': duration_ms,
                'reason': 'request_exception',
                'exception_type': type(e).__name__,
                'bypass_method': 'allorigins'
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Request error sending message to {to}: {str(e)}")

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        response_data["duration_ms"] = duration_ms
        error_msg = f"Unexpected error occurred: {str(e)}"
        stack_trace = traceback.format_exc()

        response_data.update({
            "message": "Unexpected error occurred",
            "error": error_msg
        })

        log_message_activity(
            'MESSAGE_FAILED',
            f"Unexpected message error to {to}",
            client=client,
            metadata={
                'recipient': to,
                'message_length': len(conversation),
                'duration_ms': duration_ms,
                'reason': 'unexpected_error',
                'exception_type': type(e).__name__,
                'stack_trace': stack_trace,
                'bypass_method': 'allorigins'
            },
            level='ERROR',
            error_message=error_msg
        )

        logger.error(f"Unexpected error sending message to {to}: {str(e)}")

    return response_data