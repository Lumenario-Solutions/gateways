from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
import json
from .models import (
    ActivityLog,
    Notification,
    ClientEnvironmentVariable,
    ClientTemplate
)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Admin interface for ActivityLog model with comprehensive filtering and display."""

    list_display = [
        'activity_type', 'description_short', 'client_link', 'user_link',
        'level', 'ip_address', 'created_at', 'duration_display'
    ]
    list_filter = [
        'activity_type', 'level', 'created_at',
        ('client', admin.RelatedOnlyFieldListFilter),
        ('user', admin.RelatedOnlyFieldListFilter),
        'ip_address'
    ]
    search_fields = [
        'activity_type', 'description', 'client__name', 'user__username',
        'ip_address', 'error_message'
    ]
    readonly_fields = [
        'log_id', 'created_at', 'metadata_display', 'error_display',
        'duration_display', 'activity_type_badge'
    ]

    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_per_page = 50

    fieldsets = (
        ('Basic Information', {
            'fields': ('log_id', 'activity_type_badge', 'description', 'level')
        }),
        ('Related Entities', {
            'fields': ('client', 'user')
        }),
        ('Request Context', {
            'fields': ('ip_address', 'user_agent', 'session_id', 'request_id'),
            'classes': ('collapse',)
        }),
        ('Additional Data', {
            'fields': ('metadata_display', 'duration_display'),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('error_display', 'stack_trace'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        })
    )

    def description_short(self, obj):
        """Return truncated description."""
        if len(obj.description) > 60:
            return f"{obj.description[:60]}..."
        return obj.description
    description_short.short_description = 'Description'

    def client_link(self, obj):
        """Return link to client admin."""
        if obj.client:
            url = reverse('admin:clients_client_change', args=[obj.client.client_id])
            return format_html('<a href="{}">{}</a>', url, obj.client.name)
        return '-'
    client_link.short_description = 'Client'

    def user_link(self, obj):
        """Return link to user admin."""
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = 'User'

    def metadata_display(self, obj):
        """Display formatted metadata."""
        if obj.metadata:
            formatted = json.dumps(obj.metadata, indent=2)
            return format_html('<pre style="white-space: pre-wrap;">{}</pre>', formatted)
        return 'No metadata'
    metadata_display.short_description = 'Metadata'

    def error_display(self, obj):
        """Display error message with formatting."""
        if obj.error_message:
            return format_html('<pre style="color: red; white-space: pre-wrap;">{}</pre>', obj.error_message)
        return 'No error'
    error_display.short_description = 'Error Message'

    def duration_display(self, obj):
        """Display duration in a readable format."""
        if obj.duration_ms:
            if obj.duration_ms < 1000:
                return f"{obj.duration_ms}ms"
            else:
                return f"{obj.duration_ms/1000:.2f}s"
        return '-'
    duration_display.short_description = 'Duration'

    def activity_type_badge(self, obj):
        """Display activity type with color coding."""
        color_map = {
            'ERROR': '#dc3545',
            'WARNING': '#ffc107',
            'INFO': '#28a745',
            'DEBUG': '#6c757d',
            'CRITICAL': '#dc3545'
        }

        # Get color based on level or activity type
        color = color_map.get(obj.level, '#17a2b8')
        if obj.activity_type.endswith('_FAILED'):
            color = '#dc3545'
        elif obj.activity_type.endswith('_SUCCESS') or obj.activity_type.endswith('_SUCCESSFUL'):
            color = '#28a745'

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 12px;">{}</span>',
            color, obj.get_activity_type_display()
        )
    activity_type_badge.short_description = 'Activity Type'

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('client', 'user')

    def changelist_view(self, request, extra_context=None):
        """Add custom context to changelist view."""
        extra_context = extra_context or {}

        # Add statistics
        queryset = self.get_queryset(request)

        # Recent activity stats (last 24 hours)
        last_24h = timezone.now() - timedelta(hours=24)
        recent_logs = queryset.filter(created_at__gte=last_24h)

        stats = {
            'total_logs': queryset.count(),
            'recent_logs_24h': recent_logs.count(),
            'error_logs_24h': recent_logs.filter(level__in=['ERROR', 'CRITICAL']).count(),
            'payment_activities_24h': recent_logs.filter(
                activity_type__startswith='PAYMENT'
            ).count(),
            'top_activity_types': list(
                recent_logs.values('activity_type')
                .annotate(count=Count('activity_type'))
                .order_by('-count')[:5]
            )
        }

        extra_context['activity_stats'] = stats
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Notification model."""

    list_display = [
        'title', 'client_link', 'notification_type', 'status_badge',
        'channels_display', 'is_read', 'created_at'
    ]
    list_filter = [
        'notification_type', 'status', 'is_read', 'created_at',
        ('client', admin.RelatedOnlyFieldListFilter),
        'email_sent', 'whatsapp_sent'
    ]
    search_fields = ['title', 'message', 'client__name', 'reference_id']
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'read_at',
        'email_sent_at', 'whatsapp_sent_at', 'metadata_display'
    ]

    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_per_page = 50

    fieldsets = (
        ('Basic Information', {
            'fields': ('client', 'notification_type', 'title', 'message')
        }),
        ('Delivery Status', {
            'fields': ('status', 'channels_sent', 'error_message', 'retry_count')
        }),
        ('Channel Status', {
            'fields': ('email_sent', 'email_sent_at', 'whatsapp_sent', 'whatsapp_sent_at'),
            'classes': ('collapse',)
        }),
        ('Read Status', {
            'fields': ('is_read', 'read_at')
        }),
        ('Reference & Metadata', {
            'fields': ('reference_id', 'metadata_display'),
            'classes': ('collapse',)
        }),
        ('Scheduling', {
            'fields': ('scheduled_for',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def client_link(self, obj):
        """Return link to client admin."""
        if obj.client:
            url = reverse('admin:clients_client_change', args=[obj.client.client_id])
            return format_html('<a href="{}">{}</a>', url, obj.client.name)
        return '-'
    client_link.short_description = 'Client'

    def status_badge(self, obj):
        """Display status with color coding."""
        color_map = {
            'PENDING': '#ffc107',
            'SENT': '#28a745',
            'FAILED': '#dc3545',
            'DELIVERED': '#17a2b8'
        }
        color = color_map.get(obj.status, '#6c757d')

        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def channels_display(self, obj):
        """Display sent channels as badges."""
        if not obj.channels_sent:
            return format_html('<span style="color: #6c757d;">None</span>')

        badges = []
        for channel in obj.channels_sent:
            color = '#28a745' if channel in obj.channels_sent else '#6c757d'
            badges.append(
                f'<span style="background-color: {color}; color: white; '
                f'padding: 1px 4px; border-radius: 2px; font-size: 10px; '
                f'margin-right: 2px;">{channel}</span>'
            )

        return format_html(''.join(badges))
    channels_display.short_description = 'Channels'

    def metadata_display(self, obj):
        """Display formatted metadata."""
        if obj.metadata:
            formatted = json.dumps(obj.metadata, indent=2)
            return format_html('<pre style="white-space: pre-wrap;">{}</pre>', formatted)
        return 'No metadata'
    metadata_display.short_description = 'Metadata'

    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request).select_related('client')

    actions = ['mark_as_read', 'retry_failed_notifications']

    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read."""
        count = 0
        for notification in queryset:
            if not notification.is_read:
                notification.mark_as_read()
                count += 1

        self.message_user(request, f"Marked {count} notifications as read.")
    mark_as_read.short_description = "Mark selected notifications as read"

    def retry_failed_notifications(self, request, queryset):
        """Retry failed notifications."""
        failed_notifications = queryset.filter(status='FAILED')
        count = failed_notifications.count()

        for notification in failed_notifications:
            # Reset status to pending for retry
            notification.status = 'PENDING'
            notification.retry_count = 0
            notification.error_message = ''
            notification.save()

        self.message_user(request, f"Reset {count} failed notifications for retry.")
    retry_failed_notifications.short_description = "Retry failed notifications"


@admin.register(ClientEnvironmentVariable)
class ClientEnvironmentVariableAdmin(admin.ModelAdmin):
    """Admin interface for ClientEnvironmentVariable model."""

    list_display = [
        'client_link', 'variable_type', 'custom_name', 'description_short',
        'is_active', 'created_at'
    ]
    list_filter = [
        'variable_type', 'is_active', 'created_at',
        ('client', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = ['client__name', 'variable_type', 'custom_name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at', 'encrypted_value_display']

    fieldsets = (
        ('Basic Information', {
            'fields': ('client', 'variable_type', 'custom_name', 'description')
        }),
        ('Value', {
            'fields': ('encrypted_value_display',),
            'description': 'The actual value is encrypted and cannot be displayed for security.'
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def client_link(self, obj):
        """Return link to client admin."""
        url = reverse('admin:clients_client_change', args=[obj.client.client_id])
        return format_html('<a href="{}">{}</a>', url, obj.client.name)
    client_link.short_description = 'Client'

    def description_short(self, obj):
        """Return truncated description."""
        if obj.description and len(obj.description) > 50:
            return f"{obj.description[:50]}..."
        return obj.description or '-'
    description_short.short_description = 'Description'

    def encrypted_value_display(self, obj):
        """Display encrypted value info."""
        if obj.encrypted_value:
            return format_html(
                '<span style="color: #6c757d; font-style: italic;">'
                'Encrypted value (length: {} characters)</span>',
                len(obj.encrypted_value)
            )
        return 'No value set'
    encrypted_value_display.short_description = 'Encrypted Value'

    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request).select_related('client')

    def save_model(self, request, obj, form, change):
        """Log environment variable changes."""
        super().save_model(request, obj, form, change)

        # Log the activity
        try:
            from .models import ActivityLog
            action = 'updated' if change else 'created'
            ActivityLog.objects.log_client_activity(
                client=obj.client,
                activity_type='ENV_VAR_UPDATED',
                description=f"Environment variable {action}: {obj.get_variable_name()}",
                user=request.user,
                metadata={
                    'variable_type': obj.variable_type,
                    'variable_name': obj.get_variable_name(),
                    'is_active': obj.is_active,
                    'action': action
                }
            )
        except Exception as e:
            # Don't fail the save if logging fails
            pass


@admin.register(ClientTemplate)
class ClientTemplateAdmin(admin.ModelAdmin):
    """Admin interface for ClientTemplate model."""

    list_display = [
        'name', 'client_link', 'template_type', 'is_active',
        'validation_status', 'last_used', 'created_at'
    ]
    list_filter = [
        'template_type', 'is_active', 'created_at', 'last_used',
        ('client', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = ['name', 'description', 'client__name']
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'last_used',
        'available_parameters_display', 'validation_result_display',
        'content_preview'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('client', 'template_type', 'name', 'description')
        }),
        ('Template Content', {
            'fields': ('html_content', 'content_preview'),
            'description': 'Use Django template syntax with available parameters.'
        }),
        ('Parameters & Validation', {
            'fields': ('available_parameters_display', 'validation_result_display'),
            'classes': ('collapse',),
            'description': 'Available parameters and template validation results.'
        }),
        ('Status & Usage', {
            'fields': ('is_active', 'last_used')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def client_link(self, obj):
        """Return link to client admin."""
        url = reverse('admin:clients_client_change', args=[obj.client.client_id])
        return format_html('<a href="{}">{}</a>', url, obj.client.name)
    client_link.short_description = 'Client'

    def validation_status(self, obj):
        """Display template validation status."""
        try:
            result = obj.validate_template()
            if result['success']:
                return format_html(
                    '<span style="background-color: #28a745; color: white; '
                    'padding: 2px 6px; border-radius: 3px; font-size: 11px;">Valid</span>'
                )
            else:
                return format_html(
                    '<span style="background-color: #dc3545; color: white; '
                    'padding: 2px 6px; border-radius: 3px; font-size: 11px;">Invalid</span>'
                )
        except Exception:
            return format_html(
                '<span style="background-color: #ffc107; color: black; '
                'padding: 2px 6px; border-radius: 3px; font-size: 11px;">Error</span>'
            )
    validation_status.short_description = 'Validation'

    def available_parameters_display(self, obj):
        """Display available parameters."""
        params = obj.get_available_parameters()
        if params:
            param_list = ', '.join([f"<code>{{{{{param}}}}}</code>" for param in params])
            return format_html(param_list)
        return 'No parameters available'
    available_parameters_display.short_description = 'Available Parameters'

    def validation_result_display(self, obj):
        """Display validation result."""
        try:
            result = obj.validate_template()
            if result['success']:
                return format_html(
                    '<span style="color: #28a745;">✓ Template is valid</span>'
                )
            else:
                errors = '<br>'.join([f"• {error}" for error in result['errors']])
                return format_html(
                    '<div style="color: #dc3545;">✗ Template has errors:<br>{}</div>',
                    errors
                )
        except Exception as e:
            return format_html(
                '<span style="color: #ffc107;">⚠ Validation error: {}</span>',
                str(e)
            )
    validation_result_display.short_description = 'Validation Result'

    def content_preview(self, obj):
        """Display content preview."""
        if obj.html_content:
            # Show first 200 characters
            preview = obj.html_content[:200]
            if len(obj.html_content) > 200:
                preview += '...'

            # Remove HTML tags for preview
            import re
            text_preview = re.sub(r'<[^>]+>', '', preview)

            return format_html(
                '<div style="background-color: #f8f9fa; padding: 10px; '
                'border: 1px solid #dee2e6; border-radius: 4px; '
                'font-family: monospace; font-size: 12px; max-height: 100px; '
                'overflow-y: auto;">{}</div>',
                text_preview
            )
        return 'No content'
    content_preview.short_description = 'Content Preview'

    def get_queryset(self, request):
        """Optimize queryset."""
        return super().get_queryset(request).select_related('client')

    actions = ['validate_templates', 'activate_templates', 'deactivate_templates']

    def validate_templates(self, request, queryset):
        """Validate selected templates."""
        valid_count = 0
        invalid_count = 0

        for template in queryset:
            try:
                result = template.validate_template()
                if result['success']:
                    valid_count += 1
                else:
                    invalid_count += 1
            except Exception:
                invalid_count += 1

        self.message_user(
            request,
            f"Validation completed: {valid_count} valid, {invalid_count} invalid templates."
        )
    validate_templates.short_description = "Validate selected templates"

    def activate_templates(self, request, queryset):
        """Activate selected templates."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} templates.")
    activate_templates.short_description = "Activate selected templates"

    def deactivate_templates(self, request, queryset):
        """Deactivate selected templates."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} templates.")
    deactivate_templates.short_description = "Deactivate selected templates"

    def save_model(self, request, obj, form, change):
        """Log template changes."""
        super().save_model(request, obj, form, change)

        # Log the activity
        try:
            from .models import ActivityLog
            action = 'updated' if change else 'created'
            ActivityLog.objects.log_client_activity(
                client=obj.client,
                activity_type='MODEL_UPDATED' if change else 'MODEL_CREATED',
                description=f"Template {action}: {obj.name} ({obj.get_template_type_display()})",
                user=request.user,
                metadata={
                    'template_id': str(obj.id),
                    'template_type': obj.template_type,
                    'template_name': obj.name,
                    'is_active': obj.is_active,
                    'action': action
                }
            )
        except Exception:
            # Don't fail the save if logging fails
            pass


# Custom admin site header and title
admin.site.site_header = "Payment Gateway Administration"
admin.site.site_title = "Payment Gateway Admin"
admin.site.index_title = "Welcome to Payment Gateway Administration"
