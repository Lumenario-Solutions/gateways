"""
MPesa API v1 serializers for request/response validation and data transformation.
"""

from rest_framework import serializers
from decimal import Decimal
from mpesa.models import Transaction, CallbackLog
from core.utils.phone import normalize_phone_number, PhoneNumberError
import uuid


class STKPushInitiateSerializer(serializers.Serializer):
    """Serializer for STK Push initiation requests."""

    phone_number = serializers.CharField(
        max_length=15,
        help_text="Phone number in format 254XXXXXXXXX or 0XXXXXXXXX"
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('1.00'),
        max_value=Decimal('100000.00'),
        help_text="Transaction amount (KES 1.00 - 100,000.00)"
    )
    description = serializers.CharField(
        max_length=255,
        help_text="Transaction description/purpose"
    )
    reference = serializers.CharField(
        max_length=100,
        required=False,
        help_text="Optional client transaction reference"
    )
    account_reference = serializers.CharField(
        max_length=50,
        required=False,
        help_text="Account reference (shown to user)"
    )

    def validate_phone_number(self, value):
        """Validate and normalize phone number."""
        try:
            return normalize_phone_number(value)
        except PhoneNumberError as e:
            raise serializers.ValidationError(f"Invalid phone number: {e}")

    def validate_amount(self, value):
        """Validate transaction amount."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value

    def validate_description(self, value):
        """Validate description length and content."""
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Description must be at least 3 characters")
        return value.strip()


class STKPushResponseSerializer(serializers.Serializer):
    """Serializer for STK Push response."""

    transaction_id = serializers.UUIDField(read_only=True)
    checkout_request_id = serializers.CharField(read_only=True)
    merchant_request_id = serializers.CharField(read_only=True)
    response_code = serializers.CharField(read_only=True)
    response_description = serializers.CharField(read_only=True)
    customer_message = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status responses."""

    transaction_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    description = serializers.CharField(read_only=True)
    reference = serializers.CharField(read_only=True)

    # MPesa specific fields
    checkout_request_id = serializers.CharField(read_only=True, allow_null=True)
    merchant_request_id = serializers.CharField(read_only=True, allow_null=True)
    mpesa_receipt_number = serializers.CharField(read_only=True, allow_null=True)
    transaction_date = serializers.DateTimeField(read_only=True, allow_null=True)

    # Response details
    response_code = serializers.CharField(read_only=True, allow_null=True)
    response_description = serializers.CharField(read_only=True, allow_null=True)

    # Timestamps
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    # Callback status
    callback_received = serializers.BooleanField(read_only=True)


class MPesaCallbackSerializer(serializers.Serializer):
    """Serializer for MPesa callback data validation."""

    Body = serializers.DictField()

    def validate_Body(self, value):
        """Validate callback body structure."""
        if 'stkCallback' not in value:
            raise serializers.ValidationError("Missing stkCallback in request body")

        stk_callback = value['stkCallback']
        required_fields = ['MerchantRequestID', 'CheckoutRequestID', 'ResultCode', 'ResultDesc']

        for field in required_fields:
            if field not in stk_callback:
                raise serializers.ValidationError(f"Missing required field: {field}")

        return value


class ManualValidationSerializer(serializers.Serializer):
    """Serializer for manual payment validation (Paybill/Till)."""

    PAYMENT_METHODS = [
        ('PAYBILL', 'Paybill'),
        ('BUYGOODS', 'Buy Goods (Till)'),
        ('SEND_MONEY', 'Send Money'),
    ]

    transaction_type = serializers.ChoiceField(choices=PAYMENT_METHODS)
    mpesa_receipt_number = serializers.CharField(
        max_length=50,
        help_text="MPesa transaction receipt number"
    )
    phone_number = serializers.CharField(
        max_length=15,
        help_text="Customer phone number"
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('1.00'),
        help_text="Transaction amount"
    )
    account_reference = serializers.CharField(
        max_length=50,
        required=False,
        help_text="Account reference used by customer"
    )
    transaction_date = serializers.DateTimeField(
        help_text="When the transaction occurred"
    )
    description = serializers.CharField(
        max_length=255,
        required=False,
        default="Manual payment validation"
    )

    def validate_phone_number(self, value):
        """Validate and normalize phone number."""
        try:
            return normalize_phone_number(value)
        except PhoneNumberError as e:
            raise serializers.ValidationError(f"Invalid phone number: {e}")

    def validate_mpesa_receipt_number(self, value):
        """Validate MPesa receipt number format."""
        if not value or len(value) < 5:
            raise serializers.ValidationError("Invalid MPesa receipt number")
        return value.upper()


class TransactionListSerializer(serializers.ModelSerializer):
    """Serializer for transaction list views."""

    class Meta:
        model = Transaction
        fields = [
            'transaction_id', 'transaction_type', 'phone_number', 'amount',
            'description', 'reference', 'status', 'mpesa_receipt_number',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['transaction_id', 'created_at', 'updated_at']


class TransactionDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed transaction views."""

    class Meta:
        model = Transaction
        exclude = ['client', 'callback_data', 'ip_address', 'user_agent']
        read_only_fields = ['transaction_id', 'created_at', 'updated_at']


class ErrorResponseSerializer(serializers.Serializer):
    """Serializer for error responses."""

    error = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    details = serializers.DictField(read_only=True, required=False)
    timestamp = serializers.DateTimeField(read_only=True)
    request_id = serializers.CharField(read_only=True, required=False)


class SuccessResponseSerializer(serializers.Serializer):
    """Serializer for success responses."""

    success = serializers.BooleanField(read_only=True, default=True)
    message = serializers.CharField(read_only=True)
    data = serializers.DictField(read_only=True, required=False)
    timestamp = serializers.DateTimeField(read_only=True)


class HealthCheckSerializer(serializers.Serializer):
    """Serializer for health check responses."""

    status = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    services = serializers.DictField(read_only=True)
    timestamp = serializers.DateTimeField(read_only=True)


class ConnectionTestSerializer(serializers.Serializer):
    """Serializer for MPesa connection test."""

    environment = serializers.ChoiceField(
        choices=[('sandbox', 'Sandbox'), ('live', 'Live')],
        default='sandbox'
    )


class BulkStatusCheckSerializer(serializers.Serializer):
    """Serializer for bulk status checking."""

    transaction_ids = serializers.ListField(
        child=serializers.UUIDField(),
        max_length=50,
        help_text="List of transaction IDs to check (max 50)"
    )

    def validate_transaction_ids(self, value):
        """Validate transaction IDs list."""
        if not value:
            raise serializers.ValidationError("At least one transaction ID is required")

        if len(value) > 50:
            raise serializers.ValidationError("Maximum 50 transaction IDs allowed")

        # Check for duplicates
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate transaction IDs found")

        return value


class WebhookConfigurationSerializer(serializers.Serializer):
    """Serializer for webhook configuration."""

    webhook_url = serializers.URLField(
        help_text="URL to receive webhook notifications"
    )
    webhook_secret = serializers.CharField(
        max_length=255,
        required=False,
        help_text="Secret for webhook signature verification"
    )
    events = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            ('payment.successful', 'Payment Successful'),
            ('payment.failed', 'Payment Failed'),
            ('payment.pending', 'Payment Pending'),
        ]),
        default=['payment.successful', 'payment.failed']
    )


class PaymentSummarySerializer(serializers.Serializer):
    """Serializer for payment summary statistics."""

    total_transactions = serializers.IntegerField(read_only=True)
    successful_transactions = serializers.IntegerField(read_only=True)
    failed_transactions = serializers.IntegerField(read_only=True)
    pending_transactions = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    successful_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    period_start = serializers.DateTimeField(read_only=True)
    period_end = serializers.DateTimeField(read_only=True)


class TransactionRefundSerializer(serializers.Serializer):
    """Serializer for transaction refund requests."""

    reason = serializers.CharField(
        max_length=255,
        help_text="Reason for refund"
    )
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="Partial refund amount (optional)"
    )

    def validate_amount(self, value):
        """Validate refund amount."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Refund amount must be greater than 0")
        return value
