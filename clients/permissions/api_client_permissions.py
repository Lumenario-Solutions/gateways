"""
Custom permission classes for API key authentication.

These permissions work with Client objects returned by API key authentication,
replacing Django's default user-based permissions.
"""

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _
from clients.models import Client
import logging

logger = logging.getLogger(__name__)


class IsValidClient(BasePermission):
    """
    Permission class that ensures request.user is a valid, active Client.

    This replaces Django's IsAuthenticated permission for API key authentication.
    """

    message = _('Valid API key authentication required.')

    def has_permission(self, request, view):
        """
        Check if the request has a valid, active client.

        Args:
            request: The HTTP request object
            view: The view being accessed

        Returns:
            bool: True if client is valid and active
        """
        # Check if user exists and is authenticated
        if not request.user:
            return False

        # Ensure request.user is a Client instance, not a Django User
        if not isinstance(request.user, Client):
            logger.warning(f"Invalid user type in request: {type(request.user)}")
            return False

        # Check if client has required attributes
        if not hasattr(request.user, 'client_id'):
            logger.warning("Request user is missing client_id attribute")
            return False

        # Check if client is active
        if not request.user.is_active():
            logger.warning(f"Inactive client attempted access: {request.user.client_id}")
            return False

        return True

    def has_object_permission(self, request, view, obj):
        """
        Check if the client has permission to access this specific object.

        Args:
            request: The HTTP request object
            view: The view being accessed
            obj: The object being accessed

        Returns:
            bool: True if client has permission to access the object
        """
        # First check basic client permission
        if not self.has_permission(request, view):
            return False

        # If object has a client field, ensure it matches the requesting client
        if hasattr(obj, 'client'):
            return obj.client == request.user

        # If object has a client_id field, ensure it matches
        if hasattr(obj, 'client_id'):
            return obj.client_id == request.user.client_id

        # Default to allowing access if no client relationship
        return True


class ClientOwnerPermission(BasePermission):
    """
    Permission class that ensures the client owns the requested resource.

    This is used for endpoints where clients should only access their own data.
    """

    message = _('You can only access your own resources.')

    def has_permission(self, request, view):
        """Check basic client validity."""
        return IsValidClient().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """
        Check if the client owns this object.

        Args:
            request: The HTTP request object
            view: The view being accessed
            obj: The object being accessed

        Returns:
            bool: True if client owns the object
        """
        # Basic client check
        if not self.has_permission(request, view):
            return False

        client = request.user

        # Check direct client relationship
        if hasattr(obj, 'client'):
            if obj.client != client:
                logger.warning(f"Client {client.client_id} attempted to access resource owned by {obj.client.client_id}")
                return False
            return True

        # Check client_id relationship
        if hasattr(obj, 'client_id'):
            if obj.client_id != client.client_id:
                logger.warning(f"Client {client.client_id} attempted to access resource with client_id {obj.client_id}")
                return False
            return True

        # If no client relationship, deny access for security
        logger.warning(f"Object {type(obj).__name__} has no client relationship - denying access")
        return False


class ClientIPPermission(BasePermission):
    """
    Permission class that checks if the request IP is whitelisted for the client.
    """

    message = _('Your IP address is not whitelisted for this client.')

    def has_permission(self, request, view):
        """
        Check if the client's IP is whitelisted.

        Args:
            request: The HTTP request object
            view: The view being accessed

        Returns:
            bool: True if IP is allowed
        """
        # First check basic client validity
        if not IsValidClient().has_permission(request, view):
            return False

        client = request.user

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Check if IP is allowed
        if not client.is_ip_allowed(client_ip):
            logger.warning(f"IP {client_ip} not whitelisted for client {client.client_id}")
            return False

        return True

    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class ClientPlanPermission(BasePermission):
    """
    Permission class that checks if the client's plan allows access to specific features.
    """

    def __init__(self, required_plans=None):
        """
        Initialize with required plans.

        Args:
            required_plans (list): List of plan names that are allowed
        """
        self.required_plans = required_plans or ['free', 'basic', 'premium', 'enterprise']

    def has_permission(self, request, view):
        """
        Check if the client's plan allows access.

        Args:
            request: The HTTP request object
            view: The view being accessed

        Returns:
            bool: True if client's plan is allowed
        """
        # First check basic client validity
        if not IsValidClient().has_permission(request, view):
            return False

        client = request.user

        # Check if client's plan is in allowed plans
        if client.plan not in self.required_plans:
            logger.warning(f"Client {client.client_id} with plan {client.plan} attempted to access restricted feature")
            return False

        return True


class APIKeyPermission(BasePermission):
    """
    Permission class that validates API key permissions and scopes.
    """

    def __init__(self, required_permissions=None):
        """
        Initialize with required permissions.

        Args:
            required_permissions (list): List of required permission strings
        """
        self.required_permissions = required_permissions or []

    def has_permission(self, request, view):
        """
        Check if the API key has required permissions.

        Args:
            request: The HTTP request object
            view: The view being accessed

        Returns:
            bool: True if API key has required permissions
        """
        # First check basic client validity
        if not IsValidClient().has_permission(request, view):
            return False

        # If no specific permissions required, allow access
        if not self.required_permissions:
            return True

        # For now, we'll implement basic permission checking
        # This can be extended when ClientAPIKey permissions are used
        client = request.user

        # Log permission check for audit
        logger.info(f"Permission check for client {client.client_id}: {self.required_permissions}")

        # For basic implementation, allow all access
        # This should be enhanced based on ClientAPIKey.permissions field
        return True


# Convenience permission combinations
class IsValidClientWithIP(BasePermission):
    """Combined permission for valid client with IP checking."""

    def has_permission(self, request, view):
        """Check both client validity and IP whitelist."""
        return (IsValidClient().has_permission(request, view) and
                ClientIPPermission().has_permission(request, view))


class IsClientOwnerWithIP(BasePermission):
    """Combined permission for client ownership with IP checking."""

    def has_permission(self, request, view):
        """Check client validity and IP whitelist."""
        return IsValidClientWithIP().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """Check object ownership."""
        return ClientOwnerPermission().has_object_permission(request, view, obj)
