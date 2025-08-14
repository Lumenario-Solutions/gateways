import os
import json
import requests
from django.conf import settings
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

def send_message(to: str, conversation: str) -> Dict[str, Any]:
    """
    Send a message using external API
    
    Args:
        to (str): Recipient identifier (e.g., phone number)
        conversation (str): Message content to send
        
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
    
    # Get API credentials from Django settings or environment variables
    api_url = getattr(settings, 'MESSAGE_API_URL', None) or os.getenv('API_URL')
    api_key = getattr(settings, 'MESSAGE_API_KEY', None) or os.getenv('API_KEY')
    
    if not api_url or not api_key:
        response_data.update({
            "message": "Missing API credentials",
            "error": "Set MESSAGE_API_URL and MESSAGE_API_KEY in settings or API_URL and API_KEY in environment variables"
        })
        return response_data
    
    # Prepare payload
    payload = {
        "to": to,
        "conversation": conversation
    }
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        # Send POST request
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        # Try to parse JSON response, fallback to text
        try:
            api_response_data = response.json()
        except json.JSONDecodeError:
            api_response_data = {"raw_response": response.text}
        
        # Check if request was successful (status code 2xx)
        if response.status_code >= 200 and response.status_code < 300:
            response_data.update({
                "success": True,
                "message": "Message sent successfully",
                "data": api_response_data
            })
            logger.info(f"Message sent successfully to {to}. Status: {response.status_code}")
            print(f"Success: {response.text}")  # Keep original behavior
        else:
            response_data.update({
                "message": f"API request failed with status {response.status_code}",
                "error": f"HTTP {response.status_code}: {response.text}",
                "data": api_response_data
            })
            logger.error(f"API request failed for {to}. Status: {response.status_code}, Response: {response.text}")
        
    except requests.exceptions.Timeout:
        response_data.update({
            "message": "Request timeout",
            "error": "The request took too long to complete"
        })
        logger.error(f"Timeout error sending message to {to}")
        
    except requests.exceptions.ConnectionError:
        response_data.update({
            "message": "Connection error",
            "error": "Unable to connect to the API endpoint"
        })
        logger.error(f"Connection error sending message to {to}")
        
    except requests.exceptions.RequestException as e:
        response_data.update({
            "message": "Request failed",
            "error": str(e)
        })
        logger.error(f"Request error sending message to {to}: {str(e)}")
        
    except Exception as e:
        response_data.update({
            "message": "Unexpected error occurred",
            "error": str(e)
        })
        logger.error(f"Unexpected error sending message to {to}: {str(e)}")
    
    return response_data