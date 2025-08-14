"""
Serializers for core app models.
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from clients.models import Client
from .models import ActivityLog, Notification, ClientEnvironmentVariable


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for activity logs."""

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = ['id', 'username', 'first_name', 'last_name', 'email']


class ClientBasicSerializer(serializers.ModelSerializer):
    """Basic client serializer for activity logs."""

    class Meta:
        model = Client
        fields = ['client_id', 'name', 'email', 'status', 'plan']
        read_only_fields = ['client_id', 'name', 'email', 'status', 'plan']


class ActivityLogSerializer(serializers.ModelSerializer):
    """
    Serializer for ActivityLog model - read-only.
    Provides comprehensive activity log data with related object details.
    """

    client = ClientBasicSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    is_error = serializers.BooleanField(read_only=True)
    is_security_related = serializers.BooleanField(read_only=True)
    duration_display = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = [
            'log_id',
            'activity_type',
            'activity_type_display',
            'description',
            'level',
            'level_display',
            'client',
            'user',
            'ip_address',
            'user_agent',
            'session_id',
            'request_id',
            'metadata',
            'error_message',
            'stack_trace',
            'duration_ms',
            'duration_display',
            'created_at',
            'is_error',
            'is_security_related'
        ]
        read_only_fields = fields  # All fields are read-only

    def get_duration_display(self, obj):
        """Get human-readable duration."""
        if obj.duration_ms:
            if obj.duration_ms < 1000:
                return f"{obj.duration_ms}ms"
            else:
                return f"{obj.duration_ms/1000:.2f}s"
        return None


class ActivityLogListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for activity log list view.
    Excludes heavy fields for better performance.
    """

    client_name = serializers.CharField(source='client.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    duration_display = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = [
            'log_id',
            'activity_type',
            'activity_type_display',
            'description',
            'level',
            'level_display',
            'client_name',
            'username',
            'ip_address',
            'duration_ms',
            'duration_display',
            'created_at'
        ]
        read_only_fields = fields

    def get_duration_display(self, obj):
        """Get human-readable duration."""
        if obj.duration_ms:
            if obj.duration_ms < 1000:
                return f"{obj.duration_ms}ms"
            else:
                return f"{obj.duration_ms/1000:.2f}s"
        return None


class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification model - read-only for logs endpoint.
    """

    client = ClientBasicSerializer(read_only=True)
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    client_hashtag = serializers.CharField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id',
            'client',
            'notification_type',
            'notification_type_display',
            'title',
            'message',
            'channels_sent',
            'status',
            'status_display',
            'reference_id',
            'metadata',
            'is_read',
            'read_at',
            'email_sent',
            'whatsapp_sent',
            'email_sent_at',
            'whatsapp_sent_at',
            'error_message',
            'retry_count',
            'created_at',
            'updated_at',
            'scheduled_for',
            'client_hashtag'
        ]
        read_only_fields = fields


class ClientEnvironmentVariableSerializer(serializers.ModelSerializer):
    """
    Serializer for ClientEnvironmentVariable model - read-only for logs.
    Note: encrypted_value is excluded for security.
    """

    client = ClientBasicSerializer(read_only=True)
    variable_name = serializers.CharField(source='get_variable_name', read_only=True)
    variable_type_display = serializers.CharField(source='get_variable_type_display', read_only=True)
    has_value = serializers.SerializerMethodField()

    class Meta:
        model = ClientEnvironmentVariable
        fields = [
            'id',
            'client',
            'variable_type',
            'variable_type_display',
            'variable_name',
            'custom_name',
            'description',
            'is_active',
            'has_value',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_has_value(self, obj):
        """Check if the environment variable has a value without exposing it."""
        return bool(obj.encrypted_value)


class ActivityLogStatsSerializer(serializers.Serializer):
    """
    Serializer for activity log statistics.
    """

    total_logs = serializers.IntegerField(read_only=True)
    logs_last_24h = serializers.IntegerField(read_only=True)
    logs_last_7d = serializers.IntegerField(read_only=True)
    error_logs_last_24h = serializers.IntegerField(read_only=True)
    warning_logs_last_24h = serializers.IntegerField(read_only=True)
    payment_activities_last_24h = serializers.IntegerField(read_only=True)
    top_activity_types = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )
    top_clients = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )
    activity_by_level = serializers.DictField(read_only=True)
    hourly_distribution = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )
