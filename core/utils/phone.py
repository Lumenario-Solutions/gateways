"""
Phone number validation and formatting utilities for Kenyan phone numbers.
"""

import re
import phonenumbers
from phonenumbers import geocoder, carrier
from phonenumbers.phonenumberutil import NumberParseException
import logging

logger = logging.getLogger(__name__)


class PhoneNumberError(Exception):
    """Custom exception for phone number validation errors."""
    pass


class KenyanPhoneValidator:
    """
    Validates and formats Kenyan phone numbers.
    """

    # Kenya country code
    KENYA_COUNTRY_CODE = "KE"
    KENYA_CALLING_CODE = "+254"

    # Kenyan mobile network prefixes
    SAFARICOM_PREFIXES = ["70", "71", "72", "79"]
    AIRTEL_PREFIXES = ["73", "78"]
    TELKOM_PREFIXES = ["77"]

    # All valid mobile prefixes
    MOBILE_PREFIXES = SAFARICOM_PREFIXES + AIRTEL_PREFIXES + TELKOM_PREFIXES

    def __init__(self):
        self.phone_patterns = {
            # Pattern for numbers starting with 254
            'international_254': re.compile(r'^254[0-9]{9}$'),
            # Pattern for numbers starting with +254
            'international_plus': re.compile(r'^\+254[0-9]{9}$'),
            # Pattern for numbers starting with 0
            'local_with_zero': re.compile(r'^0[0-9]{9}$'),
            # Pattern for numbers without country code or zero
            'mobile_only': re.compile(r'^[0-9]{9}$'),
        }

    def clean_phone_number(self, phone: str) -> str:
        """
        Clean phone number by removing spaces, dashes, and other characters.

        Args:
            phone (str): Raw phone number

        Returns:
            str: Cleaned phone number
        """
        if not phone:
            return ""

        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', str(phone).strip())
        return cleaned

    def normalize_to_international(self, phone: str) -> str:
        """
        Normalize phone number to international format (254XXXXXXXXX).

        Args:
            phone (str): Phone number in any format

        Returns:
            str: Phone number in international format

        Raises:
            PhoneNumberError: If phone number is invalid
        """
        try:
            cleaned_phone = self.clean_phone_number(phone)

            if not cleaned_phone:
                raise PhoneNumberError("Phone number cannot be empty")

            # Check different patterns and normalize
            if self.phone_patterns['international_254'].match(cleaned_phone):
                # Already in 254XXXXXXXXX format
                return cleaned_phone

            elif self.phone_patterns['international_plus'].match(cleaned_phone):
                # Remove the + sign
                return cleaned_phone[1:]

            elif self.phone_patterns['local_with_zero'].match(cleaned_phone):
                # Replace 0 with 254
                return "254" + cleaned_phone[1:]

            elif self.phone_patterns['mobile_only'].match(cleaned_phone):
                # Add 254 prefix
                return "254" + cleaned_phone

            else:
                raise PhoneNumberError(f"Invalid phone number format: {phone}")

        except Exception as e:
            logger.error(f"Phone normalization failed for {phone}: {e}")
            raise PhoneNumberError(f"Failed to normalize phone number: {e}")

    def format_for_display(self, phone: str) -> str:
        """
        Format phone number for display (+254 XXX XXX XXX).

        Args:
            phone (str): Phone number

        Returns:
            str: Formatted phone number
        """
        try:
            normalized = self.normalize_to_international(phone)
            # Format as +254 XXX XXX XXX
            return f"+{normalized[:3]} {normalized[3:6]} {normalized[6:9]} {normalized[9:]}"
        except PhoneNumberError:
            return phone

    def format_for_mpesa(self, phone: str) -> str:
        """
        Format phone number for MPesa API (254XXXXXXXXX).

        Args:
            phone (str): Phone number

        Returns:
            str: Phone number formatted for MPesa
        """
        return self.normalize_to_international(phone)

    def is_valid_kenyan_mobile(self, phone: str) -> bool:
        """
        Check if phone number is a valid Kenyan mobile number.

        Args:
            phone (str): Phone number to validate

        Returns:
            bool: True if valid Kenyan mobile number
        """
        try:
            normalized = self.normalize_to_international(phone)

            # Check if it's a Kenyan number (starts with 254)
            if not normalized.startswith("254"):
                return False

            # Check if the mobile prefix is valid
            mobile_prefix = normalized[3:5]  # Get the first two digits after 254

            return mobile_prefix in self.MOBILE_PREFIXES

        except Exception:
            return False

    def get_network_provider(self, phone: str) -> str:
        """
        Get the network provider for a Kenyan phone number.

        Args:
            phone (str): Phone number

        Returns:
            str: Network provider name
        """
        try:
            if not self.is_valid_kenyan_mobile(phone):
                return "Unknown"

            normalized = self.normalize_to_international(phone)
            mobile_prefix = normalized[3:5]

            if mobile_prefix in self.SAFARICOM_PREFIXES:
                return "Safaricom"
            elif mobile_prefix in self.AIRTEL_PREFIXES:
                return "Airtel"
            elif mobile_prefix in self.TELKOM_PREFIXES:
                return "Telkom"
            else:
                return "Unknown"

        except Exception:
            return "Unknown"

    def validate_with_phonenumbers(self, phone: str) -> dict:
        """
        Validate phone number using the phonenumbers library.

        Args:
            phone (str): Phone number to validate

        Returns:
            dict: Validation results
        """
        try:
            # Parse the phone number
            parsed_number = phonenumbers.parse(phone, self.KENYA_COUNTRY_CODE)

            # Validate the number
            is_valid = phonenumbers.is_valid_number(parsed_number)
            is_possible = phonenumbers.is_possible_number(parsed_number)

            # Get additional information
            region = geocoder.description_for_number(parsed_number, "en")
            network = carrier.name_for_number(parsed_number, "en")

            # Format the number
            international_format = phonenumbers.format_number(
                parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            national_format = phonenumbers.format_number(
                parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL
            )
            e164_format = phonenumbers.format_number(
                parsed_number, phonenumbers.PhoneNumberFormat.E164
            )

            return {
                "is_valid": is_valid,
                "is_possible": is_possible,
                "region": region,
                "network": network,
                "international_format": international_format,
                "national_format": national_format,
                "e164_format": e164_format,
                "country_code": parsed_number.country_code,
                "national_number": parsed_number.national_number,
            }

        except NumberParseException as e:
            logger.error(f"Phone number parsing failed: {e}")
            return {
                "is_valid": False,
                "is_possible": False,
                "error": str(e),
                "region": "",
                "network": "",
                "international_format": "",
                "national_format": "",
                "e164_format": "",
                "country_code": None,
                "national_number": None,
            }
        except Exception as e:
            logger.error(f"Phone number validation failed: {e}")
            return {
                "is_valid": False,
                "is_possible": False,
                "error": str(e),
                "region": "",
                "network": "",
                "international_format": "",
                "national_format": "",
                "e164_format": "",
                "country_code": None,
                "national_number": None,
            }


# Global phone validator instance
phone_validator = KenyanPhoneValidator()


def validate_phone_number(phone: str) -> dict:
    """
    Comprehensive phone number validation.

    Args:
        phone (str): Phone number to validate

    Returns:
        dict: Validation results
    """
    validator = KenyanPhoneValidator()

    # Basic validation
    is_valid_mobile = validator.is_valid_kenyan_mobile(phone)
    provider = validator.get_network_provider(phone)

    # Advanced validation with phonenumbers library
    phonenumbers_result = validator.validate_with_phonenumbers(phone)

    try:
        normalized = validator.normalize_to_international(phone)
        formatted_display = validator.format_for_display(phone)
        formatted_mpesa = validator.format_for_mpesa(phone)
    except PhoneNumberError as e:
        normalized = ""
        formatted_display = phone
        formatted_mpesa = ""

    return {
        "original": phone,
        "is_valid": is_valid_mobile and phonenumbers_result.get("is_valid", False),
        "is_kenyan_mobile": is_valid_mobile,
        "provider": provider,
        "normalized": normalized,
        "formatted_display": formatted_display,
        "formatted_mpesa": formatted_mpesa,
        "phonenumbers_validation": phonenumbers_result,
    }


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to international format.

    Args:
        phone (str): Phone number to normalize

    Returns:
        str: Normalized phone number

    Raises:
        PhoneNumberError: If phone number is invalid
    """
    return phone_validator.normalize_to_international(phone)


def format_phone_for_mpesa(phone: str) -> str:
    """
    Format phone number for MPesa API.

    Args:
        phone (str): Phone number to format

    Returns:
        str: Phone number formatted for MPesa

    Raises:
        PhoneNumberError: If phone number is invalid
    """
    return phone_validator.format_for_mpesa(phone)


def is_valid_kenyan_mobile(phone: str) -> bool:
    """
    Check if phone number is a valid Kenyan mobile number.

    Args:
        phone (str): Phone number to validate

    Returns:
        bool: True if valid Kenyan mobile number
    """
    return phone_validator.is_valid_kenyan_mobile(phone)
