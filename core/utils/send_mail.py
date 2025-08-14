import os
import json
import requests
from django.conf import settings
from typing import Dict, Any, List, Union
import logging

logger = logging.getLogger(__name__)

def send_email(to: Union[str, List[str]], subject: str, content: str,
               from_email: str = None, reply_to: str = None, client=None) -> Dict[str, Any]:
    """
    Send an email using Resend API

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
            "error": str or None
        }
    """
    # Initialize response structure
    response_data = {
        "success": False,
        "message": "",
        "data": None,
        "error": None
    }

    # Get API key - try client-specific first, then fallback to global
    api_key = None
    if client:
        try:
            from core.models import ClientEnvironmentVariable
            env_var = ClientEnvironmentVariable.objects.get_variable(client, 'RESEND_API_KEY')
            if env_var:
                api_key = env_var.get_decrypted_value()
        except Exception as e:
            logger.warning(f"Could not get client-specific email API key: {e}")

    # Fallback to global settings
    if not api_key:
        api_key = getattr(settings, 'RESEND_API_KEY', None) or os.getenv('RESEND_API_KEY')

    if not api_key:
        response_data.update({
            "message": "Missing Resend API key",
            "error": "Set RESEND_API_KEY in settings or environment variables"
        })
        return response_data

    # Set default values
    if from_email is None:
        from_email = "Lumenario <noreply@lmn.co.ke>"
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
        # Send POST request to Resend API
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )

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
                "data": api_response_data
            })
            logger.info(f"Email sent successfully to {to}. ID: {email_id}")
            print(f"Email sent successfully. ID: {email_id}")  # Keep original behavior

        else:
            error_message = api_response_data.get('message', f'HTTP {response.status_code}')
            response_data.update({
                "message": f"Failed to send email: {error_message}",
                "error": f"HTTP {response.status_code}: {response.text}",
                "data": api_response_data
            })
            logger.error(f"Failed to send email to {to}. Status: {response.status_code}, Response: {response.text}")

    except requests.exceptions.Timeout:
        response_data.update({
            "message": "Request timeout",
            "error": "The email request took too long to complete"
        })
        logger.error(f"Timeout error sending email to {to}")

    except requests.exceptions.ConnectionError:
        response_data.update({
            "message": "Connection error",
            "error": "Unable to connect to Resend API"
        })
        logger.error(f"Connection error sending email to {to}")

    except requests.exceptions.RequestException as e:
        response_data.update({
            "message": "Request failed",
            "error": str(e)
        })
        logger.error(f"Request error sending email to {to}: {str(e)}")

    except Exception as e:
        response_data.update({
            "message": "Unexpected error occurred",
            "error": str(e)
        })
        logger.error(f"Unexpected error sending email to {to}: {str(e)}")

    return response_data


def send_text_email(to: Union[str, List[str]], subject: str, text_content: str,
                   from_email: str = None, reply_to: str = None) -> Dict[str, Any]:
    """
    Send a plain text email using Resend API

    Args:
        to (str or List[str]): Recipient email address(es)
        subject (str): Email subject
        text_content (str): Plain text content of the email
        from_email (str, optional): Sender email. Defaults to "Lumenario <noreply@lmn.co.ke>"
        reply_to (str, optional): Reply-to email. Defaults to "support@lmn.co.ke"

    Returns:
        Dict[str, Any]: Structured response with success boolean and additional data
    """
    # Initialize response structure
    response_data = {
        "success": False,
        "message": "",
        "data": None,
        "error": None
    }

    # Get API key from Django settings or environment variables
    api_key = getattr(settings, 'RESEND_API_KEY', None) or os.getenv('RESEND_API_KEY')

    if not api_key:
        response_data.update({
            "message": "Missing Resend API key",
            "error": "Set RESEND_API_KEY in settings or environment variables"
        })
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

    try:
        # Send POST request to Resend API
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )

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
                "data": api_response_data
            })
            logger.info(f"Text email sent successfully to {to}. ID: {email_id}")
            print(f"Email sent successfully. ID: {email_id}")

        else:
            error_message = api_response_data.get('message', f'HTTP {response.status_code}')
            response_data.update({
                "message": f"Failed to send email: {error_message}",
                "error": f"HTTP {response.status_code}: {response.text}",
                "data": api_response_data
            })
            logger.error(f"Failed to send text email to {to}. Status: {response.status_code}")

    except Exception as e:
        response_data.update({
            "message": "Unexpected error occurred",
            "error": str(e)
        })
        logger.error(f"Unexpected error sending text email to {to}: {str(e)}")

    return response_data
