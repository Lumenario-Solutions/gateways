"""
Encryption utilities for secure credential storage and data protection.
"""

import base64
import hashlib
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    Handles encryption and decryption of sensitive data.
    """

    def __init__(self):
        self.fernet_key = self._get_fernet_key()
        self.encryption_key = self._get_encryption_key()

    def _get_fernet_key(self):
        """Get or generate Fernet key for encryption."""
        fernet_key = getattr(settings, 'ENCRYPTION_CONFIG', {}).get('FERNET_KEY')
        if not fernet_key:
            # Generate a new key if not provided
            fernet_key = Fernet.generate_key()
            logger.warning("No FERNET_KEY provided, generated a new one. Please add it to your environment variables.")

        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode()

        return Fernet(fernet_key)

    def _get_encryption_key(self):
        """Get encryption key from settings."""
        key = getattr(settings, 'ENCRYPTION_CONFIG', {}).get('ENCRYPTION_KEY')
        if not key:
            # Generate a 32-character key if not provided
            key = base64.urlsafe_b64encode(os.urandom(32)).decode()[:32]
            logger.warning("No ENCRYPTION_KEY provided, generated a new one. Please add it to your environment variables.")

        return key.encode()[:32]  # Ensure 32 bytes for AES-256

    def encrypt_data(self, data: str) -> str:
        """
        Encrypt data using Fernet encryption.

        Args:
            data (str): The data to encrypt

        Returns:
            str: Base64 encoded encrypted data
        """
        try:
            if not data:
                return ""

            encrypted_data = self.fernet_key.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt data: {e}")

    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decrypt data using Fernet encryption.

        Args:
            encrypted_data (str): Base64 encoded encrypted data

        Returns:
            str: Decrypted data
        """
        try:
            if not encrypted_data:
                return ""

            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.fernet_key.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt data: {e}")

    def encrypt_with_aes(self, data: str, password: str = None) -> dict:
        """
        Encrypt data using AES encryption with a password.

        Args:
            data (str): The data to encrypt
            password (str): Optional password for encryption

        Returns:
            dict: Contains encrypted data, salt, and IV
        """
        try:
            if not data:
                return {"encrypted_data": "", "salt": "", "iv": ""}

            # Use provided password or default encryption key
            if password:
                password = password.encode()
            else:
                password = self.encryption_key

            # Generate salt and IV
            salt = get_random_bytes(16)
            iv = get_random_bytes(16)

            # Derive key from password
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = kdf.derive(password)

            # Encrypt data
            cipher = AES.new(key, AES.MODE_CBC, iv)

            # Pad data to be multiple of 16 bytes
            pad_length = 16 - (len(data) % 16)
            padded_data = data + (chr(pad_length) * pad_length)

            encrypted_data = cipher.encrypt(padded_data.encode())

            return {
                "encrypted_data": base64.b64encode(encrypted_data).decode(),
                "salt": base64.b64encode(salt).decode(),
                "iv": base64.b64encode(iv).decode()
            }
        except Exception as e:
            logger.error(f"AES encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt with AES: {e}")

    def decrypt_with_aes(self, encrypted_dict: dict, password: str = None) -> str:
        """
        Decrypt data using AES encryption with a password.

        Args:
            encrypted_dict (dict): Contains encrypted_data, salt, and iv
            password (str): Optional password for decryption

        Returns:
            str: Decrypted data
        """
        try:
            if not encrypted_dict.get("encrypted_data"):
                return ""

            # Use provided password or default encryption key
            if password:
                password = password.encode()
            else:
                password = self.encryption_key

            # Decode components
            encrypted_data = base64.b64decode(encrypted_dict["encrypted_data"])
            salt = base64.b64decode(encrypted_dict["salt"])
            iv = base64.b64decode(encrypted_dict["iv"])

            # Derive key from password
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = kdf.derive(password)

            # Decrypt data
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted_padded = cipher.decrypt(encrypted_data)

            # Remove padding
            pad_length = decrypted_padded[-1]
            decrypted_data = decrypted_padded[:-pad_length]

            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"AES decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt with AES: {e}")

    def hash_data(self, data: str, salt: str = None) -> str:
        """
        Create a hash of the data using SHA-256.

        Args:
            data (str): The data to hash
            salt (str): Optional salt for hashing

        Returns:
            str: Hexadecimal hash
        """
        try:
            if salt:
                data = data + salt

            return hashlib.sha256(data.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Hashing failed: {e}")
            raise EncryptionError(f"Failed to hash data: {e}")

    def generate_api_key(self, length: int = 32) -> str:
        """
        Generate a secure API key.

        Args:
            length (int): Length of the API key

        Returns:
            str: Generated API key
        """
        try:
            return base64.urlsafe_b64encode(os.urandom(length)).decode()[:length]
        except Exception as e:
            logger.error(f"API key generation failed: {e}")
            raise EncryptionError(f"Failed to generate API key: {e}")

    def verify_signature(self, data: str, signature: str, secret: str) -> bool:
        """
        Verify HMAC signature for request authentication.

        Args:
            data (str): The data that was signed
            signature (str): The signature to verify
            secret (str): The secret key used for signing

        Returns:
            bool: True if signature is valid
        """
        try:
            import hmac
            expected_signature = hmac.new(
                secret.encode(),
                data.encode(),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False


class EncryptionError(Exception):
    """Custom exception for encryption-related errors."""
    pass


# Global encryption manager instance
encryption_manager = EncryptionManager()


def encrypt_mpesa_credentials(credentials: dict) -> dict:
    """
    Encrypt MPesa credentials for secure storage.

    Args:
        credentials (dict): Dictionary of MPesa credentials

    Returns:
        dict: Encrypted credentials
    """
    encrypted_creds = {}

    sensitive_fields = [
        'consumer_key', 'consumer_secret', 'passkey',
        'security_credential', 'initiator_name'
    ]

    for key, value in credentials.items():
        if key in sensitive_fields and value:
            encrypted_creds[key] = encryption_manager.encrypt_data(str(value))
        else:
            encrypted_creds[key] = value

    return encrypted_creds


def decrypt_mpesa_credentials(encrypted_credentials: dict) -> dict:
    """
    Decrypt MPesa credentials for use.

    Args:
        encrypted_credentials (dict): Dictionary of encrypted MPesa credentials

    Returns:
        dict: Decrypted credentials
    """
    decrypted_creds = {}

    sensitive_fields = [
        'consumer_key', 'consumer_secret', 'passkey',
        'security_credential', 'initiator_name'
    ]

    for key, value in encrypted_credentials.items():
        if key in sensitive_fields and value:
            try:
                decrypted_creds[key] = encryption_manager.decrypt_data(str(value))
            except EncryptionError:
                # If decryption fails, assume it's already decrypted
                decrypted_creds[key] = value
        else:
            decrypted_creds[key] = value

    return decrypted_creds
