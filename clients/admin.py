"""
Django admin configuration for clients app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Client, APIUsageLog, ClientConfiguration, ClientAPIKey


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """Admin configuration for Client model."""

    list_display = [
        'name', 'email', 'status', 'plan', 'total_transactions',
        'total_volume', 'last_api_call', 'created_at'
    ]
    list_filter = ['status', 'plan', 'created_at', 'last_api_call']
    search_fields = ['name', 'email', 'client_id']
    readonly_fields = [
        'client_id', 'api_key', 'api_secret_hash', 'total_transactions',
        'total_volume', 'last_api_call', 'created_at', 'updated_at'
    ]

    fieldsets = [
        ('Basic Information', {
            'fields': ['client_id', 'name', 'email', 'description', 'user']
        }),
        ('API Credentials', {
            'fields': ['api_key', 'api_secret_hash'],
            'classes': ['collapse']
        }),
        ('Status & Plan', {
            'fields': ['status', 'plan']
        }),
        ('Rate Limiting', {
            'fields': [
                'rate_limit_per_minute', 'rate_limit_per_hour',
                'rate_limit_per_day'
            ],
            'classes': ['collapse']
        }),
        ('Webhooks', {
            'fields': ['webhook_url', 'webhook_secret'],
            'classes': ['collapse']
        }),
        ('Security', {
            'fields': ['allowed_ips'],
            'classes': ['collapse']
        }),
        ('Financial Information', {
            'fields': ['balance', 'total_transactions', 'total_volume'],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['last_api_call', 'created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    actions = ['activate_clients', 'suspend_clients', 'disable_clients']

    def activate_clients(self, request, queryset):
        """Activate selected clients."""
        updated = queryset.update(status='active')
        self.message_user(request, f'{updated} clients activated.')
    activate_clients.short_description = "Activate selected clients"

    def suspend_clients(self, request, queryset):
        """Suspend selected clients."""
        updated = queryset.update(status='suspended')
        self.message_user(request, f'{updated} clients suspended.')
    suspend_clients.short_description = "Suspend selected clients"

    def disable_clients(self, request, queryset):
        """Disable selected clients."""
        updated = queryset.update(status='disabled')
        self.message_user(request, f'{updated} clients disabled.')
    disable_clients.short_description = "Disable selected clients"


@admin.register(APIUsageLog)
class APIUsageLogAdmin(admin.ModelAdmin):
    """Admin configuration for APIUsageLog model."""

    list_display = [
        'client', 'endpoint', 'method', 'status_code',
        'response_time', 'ip_address', 'timestamp'
    ]
    list_filter = [
        'method', 'status_code', 'timestamp',
        ('client', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = ['client__name', 'endpoint', 'ip_address']
    readonly_fields = [
        'request_id', 'client', 'endpoint', 'method', 'ip_address',
        'user_agent', 'request_size', 'response_size', 'response_time',
        'status_code', 'error_message', 'timestamp'
    ]

    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        """Disable add permission."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable change permission."""
        return False


@admin.register(ClientConfiguration)
class ClientConfigurationAdmin(admin.ModelAdmin):
    """Admin configuration for ClientConfiguration model."""

    list_display = [
        'client', 'mpesa_enabled', 'min_transaction_amount',
        'max_transaction_amount', 'require_signature'
    ]
    list_filter = [
        'mpesa_enabled', 'email_notifications', 'sms_notifications',
        'webhook_notifications', 'require_signature'
    ]
    search_fields = ['client__name']

    fieldsets = [
        ('Client', {
            'fields': ['client']
        }),
        ('MPesa Configuration', {
            'fields': [
                'mpesa_enabled', 'mpesa_shortcode', 'mpesa_passkey'
            ]
        }),
        ('Transaction Limits', {
            'fields': [
                'min_transaction_amount', 'max_transaction_amount',
                'daily_transaction_limit'
            ]
        }),
        ('Notification Settings', {
            'fields': [
                'email_notifications', 'sms_notifications',
                'webhook_notifications'
            ]
        }),
        ('Security Settings', {
            'fields': ['require_signature', 'signature_algorithm']
        }),
    ]


@admin.register(ClientAPIKey)
class ClientAPIKeyAdmin(admin.ModelAdmin):
    """Admin configuration for ClientAPIKey model."""

    list_display = [
        'client', 'name', 'environment', 'is_active',
        'last_used', 'expires_at', 'created_at'
    ]
    list_filter = [
        'environment', 'is_active', 'created_at', 'expires_at'
    ]
    search_fields = ['client__name', 'name', 'api_key']
    readonly_fields = [
        'api_key', 'api_secret_hash', 'last_used', 'created_at'
    ]

    fieldsets = [
        ('Basic Information', {
            'fields': ['client', 'name', 'environment']
        }),
        ('API Credentials', {
            'fields': ['api_key', 'api_secret_hash'],
            'classes': ['collapse']
        }),
        ('Status & Permissions', {
            'fields': ['is_active', 'permissions']
        }),
        ('Rate Limiting', {
            'fields': ['rate_limit_per_minute']
        }),
        ('Expiration', {
            'fields': ['expires_at']
        }),
        ('Usage Tracking', {
            'fields': ['last_used', 'created_at'],
            'classes': ['collapse']
        }),
    ]
