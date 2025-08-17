"""
Serializers for core app models.
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from clients.models import Client
from .models import ActivityLog, Notification, ClientEnvironmentVariable, ClientTemplate


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


class ClientTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for ClientTemplate model with validation.
    """

    client = ClientBasicSerializer(read_only=True)
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)
    available_parameters = serializers.SerializerMethodField()
    validation_result = serializers.SerializerMethodField()

    class Meta:
        model = ClientTemplate
        fields = [
            'id',
            'client',
            'template_type',
            'template_type_display',
            'name',
            'html_content',
            'description',
            'parameters',
            'is_active',
            'created_at',
            'updated_at',
            'last_used',
            'available_parameters',
            'validation_result'
        ]
        read_only_fields = ['id', 'client', 'created_at', 'updated_at', 'last_used']

    def get_available_parameters(self, obj):
        """Get list of available parameters for this template type."""
        return obj.get_available_parameters()

    def get_validation_result(self, obj):
        """Get template validation result."""
        try:
            return obj.validate_template()
        except Exception as e:
            return {
                'success': False,
                'errors': [f"Validation error: {str(e)}"]
            }

    def validate_html_content(self, value):
        """Validate HTML content."""
        if not value or not value.strip():
            raise serializers.ValidationError("HTML content cannot be empty.")

        # Basic validation for required parameters
        required_params = ['{{title}}', '{{message}}']
        missing_params = []

        for param in required_params:
            if param not in value and param.replace('{{', '{{ ').replace('}}', ' }}') not in value:
                missing_params.append(param.strip('{}').strip())

        if missing_params:
            raise serializers.ValidationError(
                f"Template must include the following parameters: {', '.join(missing_params)}"
            )

        return value

    def validate(self, attrs):
        """Cross-field validation."""
        # Ensure only one active template per type per client
        if attrs.get('is_active', True):
            client = self.context['request'].user.client if hasattr(self.context['request'].user, 'client') else None
            if not client and 'client' in self.context:
                client = self.context['client']

            if client:
                existing_active = ClientTemplate.objects.filter(
                    client=client,
                    template_type=attrs['template_type'],
                    is_active=True
                ).exclude(id=self.instance.id if self.instance else None)

                if existing_active.exists():
                    attrs['is_active'] = True  # Will deactivate others in model save()

        return attrs


class ClientTemplateListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for ClientTemplate list view.
    """

    client_name = serializers.CharField(source='client.name', read_only=True)
    template_type_display = serializers.CharField(source='get_template_type_display', read_only=True)
    content_preview = serializers.SerializerMethodField()

    class Meta:
        model = ClientTemplate
        fields = [
            'id',
            'client_name',
            'template_type',
            'template_type_display',
            'name',
            'description',
            'is_active',
            'created_at',
            'updated_at',
            'last_used',
            'content_preview'
        ]
        read_only_fields = fields

    def get_content_preview(self, obj):
        """Get preview of HTML content (first 100 characters)."""
        if obj.html_content:
            # Strip HTML tags for preview
            import re
            text_content = re.sub(r'<[^>]+>', '', obj.html_content)
            return text_content[:100] + '...' if len(text_content) > 100 else text_content
        return ''
