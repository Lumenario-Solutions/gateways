"""
Django admin configuration for MPesa app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    MpesaCredentials, Transaction, CallbackLog,
    AccessToken, MpesaConfiguration
)


@admin.register(MpesaCredentials)
class MpesaCredentialsAdmin(admin.ModelAdmin):
    """Admin configuration for MpesaCredentials model."""

    list_display = [
        'name', 'environment', 'business_shortcode',
        'is_active', 'created_at'
    ]
    list_filter = ['environment', 'is_active', 'created_at']
    search_fields = ['name', 'business_shortcode']
    readonly_fields = ['base_url', 'created_at', 'updated_at']

    fieldsets = [
        ('Basic Information', {
            'fields': ['name', 'environment', 'is_active']
        }),
        ('Credentials', {
            'fields': [
                'consumer_key', 'consumer_secret', 'business_shortcode',
                'passkey', 'initiator_name', 'security_credential'
            ],
            'description': 'Credentials are automatically encrypted when saved.'
        }),
        ('API Configuration', {
            'fields': ['base_url'],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    actions = ['activate_credentials', 'deactivate_credentials']

    def activate_credentials(self, request, queryset):
        """Activate selected credentials."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} credentials activated.')
    activate_credentials.short_description = "Activate selected credentials"

    def deactivate_credentials(self, request, queryset):
        """Deactivate selected credentials."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} credentials deactivated.')
    deactivate_credentials.short_description = "Deactivate selected credentials"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin configuration for Transaction model."""

    list_display = [
        'transaction_id', 'client', 'transaction_type', 'phone_number',
        'amount', 'status', 'mpesa_receipt_number', 'created_at'
    ]
    list_filter = [
        'transaction_type', 'status', 'callback_received',
        'created_at', 'transaction_date',
        ('client', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = [
        'transaction_id', 'phone_number', 'mpesa_receipt_number',
        'reference', 'checkout_request_id', 'client__name'
    ]
    readonly_fields = [
        'transaction_id', 'created_at', 'updated_at',
        'checkout_request_id', 'merchant_request_id'
    ]

    fieldsets = [
        ('Basic Information', {
            'fields': [
                'transaction_id', 'client', 'transaction_type',
                'phone_number', 'amount', 'description', 'reference'
            ]
        }),
        ('MPesa Details', {
            'fields': [
                'checkout_request_id', 'merchant_request_id',
                'mpesa_receipt_number', 'transaction_date'
            ],
            'classes': ['collapse']
        }),
        ('Status & Response', {
            'fields': [
                'status', 'response_code', 'response_description',
                'callback_received'
            ]
        }),
        ('Callback Data', {
            'fields': ['callback_data'],
            'classes': ['collapse']
        }),
        ('Metadata', {
            'fields': ['ip_address', 'user_agent'],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    date_hierarchy = 'created_at'

    actions = ['mark_as_successful', 'mark_as_failed', 'export_transactions']

    def mark_as_successful(self, request, queryset):
        """Mark selected transactions as successful."""
        updated = queryset.update(status='SUCCESSFUL')
        self.message_user(request, f'{updated} transactions marked as successful.')
    mark_as_successful.short_description = "Mark as successful"

    def mark_as_failed(self, request, queryset):
        """Mark selected transactions as failed."""
        updated = queryset.update(status='FAILED')
        self.message_user(request, f'{updated} transactions marked as failed.')
    mark_as_failed.short_description = "Mark as failed"

    def export_transactions(self, request, queryset):
        """Export selected transactions."""
        # This could be enhanced to generate actual export
        count = queryset.count()
        self.message_user(request, f'{count} transactions selected for export.')
    export_transactions.short_description = "Export selected transactions"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related('client')


@admin.register(CallbackLog)
class CallbackLogAdmin(admin.ModelAdmin):
    """Admin configuration for CallbackLog model."""

    list_display = [
        'log_id', 'callback_type', 'transaction', 'ip_address',
        'processed_successfully', 'received_at'
    ]
    list_filter = [
        'callback_type', 'processed_successfully', 'received_at'
    ]
    search_fields = [
        'log_id', 'ip_address', 'transaction__transaction_id'
    ]
    readonly_fields = [
        'log_id', 'transaction', 'callback_type', 'ip_address',
        'user_agent', 'headers', 'raw_data', 'processed_successfully',
        'error_message', 'received_at', 'processed_at'
    ]

    fieldsets = [
        ('Basic Information', {
            'fields': ['log_id', 'callback_type', 'transaction']
        }),
        ('Request Details', {
            'fields': ['ip_address', 'user_agent', 'headers']
        }),
        ('Processing Status', {
            'fields': [
                'processed_successfully', 'error_message',
                'received_at', 'processed_at'
            ]
        }),
        ('Raw Data', {
            'fields': ['raw_data'],
            'classes': ['collapse']
        }),
    ]

    date_hierarchy = 'received_at'

    def has_add_permission(self, request):
        """Disable add permission."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable change permission."""
        return False


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    """Admin configuration for AccessToken model."""

    list_display = [
        'environment', 'is_expired', 'expires_at', 'created_at'
    ]
    list_filter = ['environment', 'created_at', 'expires_at']
    readonly_fields = [
        'access_token', 'expires_at', 'created_at'
    ]

    fieldsets = [
        ('Token Information', {
            'fields': ['environment', 'access_token']
        }),
        ('Expiration', {
            'fields': ['expires_at', 'created_at']
        }),
    ]

    def is_expired(self, obj):
        """Show if token is expired."""
        if obj.is_expired():
            return format_html('<span style="color: red;">Expired</span>')
        else:
            return format_html('<span style="color: green;">Valid</span>')
    is_expired.short_description = 'Status'

    def has_add_permission(self, request):
        """Disable add permission."""
        return False


@admin.register(MpesaConfiguration)
class MpesaConfigurationAdmin(admin.ModelAdmin):
    """Admin configuration for MpesaConfiguration model."""

    list_display = [
        'id', 'stk_timeout_seconds', 'enable_stk_push',
        'enable_c2b', 'enable_b2c', 'updated_at'
    ]

    fieldsets = [
        ('Callback URLs', {
            'fields': [
                'stk_callback_url', 'validation_url', 'confirmation_url'
            ]
        }),
        ('Timeout Settings', {
            'fields': ['stk_timeout_seconds', 'api_timeout_seconds']
        }),
        ('Retry Settings', {
            'fields': ['max_retries', 'retry_delay_seconds']
        }),
        ('Feature Flags', {
            'fields': ['enable_stk_push', 'enable_c2b', 'enable_b2c']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    readonly_fields = ['created_at', 'updated_at']

    def has_add_permission(self, request):
        """Only allow one configuration instance."""
        return not MpesaConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Disable delete permission."""
        return False


# Custom admin site configuration
admin.site.site_header = "Lumenario Payment Gateway Admin"
admin.site.site_title = "Payment Gateway Admin"
admin.site.index_title = "Welcome to Payment Gateway Administration"
