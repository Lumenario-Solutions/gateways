"""
STK Push service for initiating MPesa payment requests.
"""

import uuid
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from mpesa.models import Transaction, MpesaConfiguration
from mpesa.services.mpesa_client import get_mpesa_client
from core.exceptions import MPesaException, ValidationException, handle_mpesa_error
from core.utils.phone import format_phone_for_mpesa, PhoneNumberError
import logging

logger = logging.getLogger(__name__)


class STKPushService:
    """
    Service for handling STK Push (Lipa na M-Pesa Online) transactions.
    """

    def __init__(self, environment='sandbox'):
        """
        Initialize STK Push service.

        Args:
            environment (str): 'sandbox' or 'live'
        """
        self.environment = environment
        self.client = get_mpesa_client(environment)
        self.config = MpesaConfiguration.get_config()

    def initiate_stk_push(self, client, phone_number, amount, description, reference=None, callback_url=None):
        """
        Initiate STK Push payment request.

        Args:
            client: Client instance making the request
            phone_number (str): Customer phone number
            amount (float): Payment amount
            description (str): Payment description
            reference (str): Optional transaction reference
            callback_url (str): Optional custom callback URL

        Returns:
            dict: STK Push response with transaction details
        """
        try:
            # Validate inputs
            self._validate_stk_push_inputs(phone_number, amount, description)

            # Format phone number
            formatted_phone = format_phone_for_mpesa(phone_number)

            # Create transaction record
            transaction = Transaction.objects.create_stk_push_transaction(
                client=client,
                phone_number=formatted_phone,
                amount=amount,
                description=description,
                reference=reference
            )

            # Prepare STK Push request
            stk_request = self._prepare_stk_push_request(
                phone_number=formatted_phone,
                amount=amount,
                description=description,
                reference=reference or str(transaction.transaction_id),
                callback_url=callback_url
            )

            # Make API request
            response = self.client.make_request('/mpesa/stkpush/v1/processrequest', stk_request)

            # Handle response
            response = handle_mpesa_error(response, transaction)

            # Update transaction with response
            self._update_transaction_with_response(transaction, response)

            # Prepare response
            result = {
                'transaction_id': str(transaction.transaction_id),
                'mpesa_checkout_request_id': response.get('CheckoutRequestID'),
                'mpesa_merchant_request_id': response.get('MerchantRequestID'),
                'response_code': response.get('ResponseCode'),
                'response_description': response.get('ResponseDescription'),
                'customer_message': response.get('CustomerMessage'),
                'phone_number': formatted_phone,
                'amount': float(amount),
                'description': description,
                'reference': reference or str(transaction.transaction_id),
                'status': 'PENDING',
                'created_at': transaction.created_at.isoformat()
            }

            logger.info(f"STK Push initiated successfully: {transaction.transaction_id}")
            return result

        except PhoneNumberError as e:
            logger.error(f"Invalid phone number for STK Push: {e}")
            raise ValidationException(f"Invalid phone number: {e}", field='phone_number')
        except MPesaException:
            raise
        except Exception as e:
            logger.error(f"Error initiating STK Push: {e}")
            raise MPesaException(f"Failed to initiate payment: {e}")

    def _validate_stk_push_inputs(self, phone_number, amount, description):
        """Validate STK Push inputs."""
        if not phone_number:
            raise ValidationException("Phone number is required", field='phone_number')

        if not amount or amount <= 0:
            raise ValidationException("Amount must be greater than 0", field='amount')

        if amount < 1:
            raise ValidationException("Minimum amount is KES 1", field='amount')

        if amount > 150000:  # MPesa limit
            raise ValidationException("Maximum amount is KES 150,000", field='amount')

        if not description:
            raise ValidationException("Description is required", field='description')

        if len(description) > 255:
            raise ValidationException("Description too long (max 255 characters)", field='description')

    def _prepare_stk_push_request(self, phone_number, amount, description, reference, callback_url=None):
        """Prepare STK Push request data."""
        try:
            # Generate password and timestamp
            password, timestamp = self.client.generate_password()

            # Use configured callback URL or default
            callback_url = callback_url or self.config.stk_callback_url

            if not callback_url:
                raise ValidationException("No callback URL configured")

            # Prepare request data
            request_data = {
                "BusinessShortCode": self.client.get_business_shortcode(),
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(float(amount)),  # Convert to integer cents
                "PartyA": phone_number,
                "PartyB": self.client.get_business_shortcode(),
                "PhoneNumber": phone_number,
                "CallBackURL": callback_url,
                "AccountReference": reference[:12] if reference else "Payment",  # Max 12 chars
                "TransactionDesc": description[:17] if description else "Payment"  # Max 17 chars
            }

            return request_data

        except Exception as e:
            logger.error(f"Error preparing STK Push request: {e}")
            raise MPesaException(f"Failed to prepare payment request: {e}")

    def _update_transaction_with_response(self, transaction, response):
        """Update transaction with STK Push response."""
        try:
            transaction.checkout_request_id = response.get('CheckoutRequestID', '')
            transaction.merchant_request_id = response.get('MerchantRequestID', '')
            transaction.response_code = response.get('ResponseCode', '')
            transaction.response_description = response.get('ResponseDescription', '')

            # Set status based on response
            if response.get('ResponseCode') == '0':
                transaction.status = 'PROCESSING'
            else:
                transaction.status = 'FAILED'

            transaction.save(update_fields=[
                'checkout_request_id', 'merchant_request_id',
                'response_code', 'response_description', 'status'
            ])

        except Exception as e:
            logger.error(f"Error updating transaction {transaction.transaction_id}: {e}")

    def query_stk_status(self, transaction_id=None, checkout_request_id=None):
        """
        Query STK Push transaction status.

        Args:
            transaction_id (str): Internal transaction ID
            checkout_request_id (str): MPesa checkout request ID

        Returns:
            dict: Transaction status information
        """
        try:
            # Get transaction
            if transaction_id:
                transaction = Transaction.objects.get(transaction_id=transaction_id)
            elif checkout_request_id:
                transaction = Transaction.objects.get(checkout_request_id=checkout_request_id)
            else:
                raise ValidationException("Either transaction_id or checkout_request_id is required")

            # If transaction is already completed, return cached status
            if transaction.status in ['SUCCESSFUL', 'FAILED', 'CANCELLED']:
                return self._format_transaction_status(transaction)

            # Query MPesa API for latest status
            status_response = self._query_mpesa_status(transaction)

            if status_response:
                # Update transaction with latest status
                self._update_transaction_with_status_response(transaction, status_response)

            return self._format_transaction_status(transaction)

        except Transaction.DoesNotExist:
            raise ValidationException("Transaction not found")
        except Exception as e:
            logger.error(f"Error querying STK status: {e}")
            raise MPesaException(f"Failed to query transaction status: {e}")

    def _query_mpesa_status(self, transaction):
        """Query MPesa API for transaction status."""
        try:
            if not transaction.checkout_request_id:
                logger.warning(f"No checkout request ID for transaction {transaction.transaction_id}")
                return None

            # Generate password and timestamp
            password, timestamp = self.client.generate_password()

            request_data = {
                "BusinessShortCode": self.client.get_business_shortcode(),
                "Password": password,
                "Timestamp": timestamp,
                "CheckoutRequestID": transaction.checkout_request_id
            }

            response = self.client.make_request('/mpesa/stkpushquery/v1/query', request_data)
            return response

        except Exception as e:
            logger.error(f"Error querying MPesa status for {transaction.transaction_id}: {e}")
            return None

    def _update_transaction_with_status_response(self, transaction, response):
        """Update transaction with status query response."""
        try:
            result_code = response.get('ResultCode')
            result_desc = response.get('ResultDesc', '')

            transaction.response_code = result_code
            transaction.response_description = result_desc

            # Update status based on result code
            if result_code == '0':
                transaction.status = 'SUCCESSFUL'
            elif result_code in ['1032', '1']:
                transaction.status = 'CANCELLED'
            else:
                transaction.status = 'FAILED'

            transaction.save(update_fields=['response_code', 'response_description', 'status'])

        except Exception as e:
            logger.error(f"Error updating transaction status: {e}")

    def _format_transaction_status(self, transaction):
        """Format transaction status for API response."""
        return {
            'transaction_id': str(transaction.transaction_id),
            'mpesa_checkout_request_id': transaction.checkout_request_id,
            'mpesa_receipt_number': transaction.mpesa_receipt_number,
            'phone_number': transaction.phone_number,
            'amount': float(transaction.amount),
            'description': transaction.description,
            'reference': transaction.reference,
            'status': transaction.status,
            'response_code': transaction.response_code,
            'response_description': transaction.response_description,
            'callback_received': transaction.callback_received,
            'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
            'created_at': transaction.created_at.isoformat(),
            'updated_at': transaction.updated_at.isoformat()
        }

    def cancel_stk_push(self, transaction_id):
        """
        Cancel pending STK Push transaction.

        Args:
            transaction_id (str): Transaction ID to cancel

        Returns:
            dict: Cancellation result
        """
        try:
            transaction = Transaction.objects.get(transaction_id=transaction_id)

            if transaction.status != 'PENDING':
                raise ValidationException(f"Cannot cancel transaction with status: {transaction.status}")

            # Update status to cancelled
            transaction.update_status('CANCELLED', response_description='Cancelled by client')

            return {
                'transaction_id': str(transaction.transaction_id),
                'status': 'CANCELLED',
                'message': 'Transaction cancelled successfully'
            }

        except Transaction.DoesNotExist:
            raise ValidationException("Transaction not found")
        except Exception as e:
            logger.error(f"Error cancelling STK Push: {e}")
            raise MPesaException(f"Failed to cancel transaction: {e}")

    def get_transaction_history(self, client, limit=50, offset=0, status=None):
        """
        Get transaction history for a client.

        Args:
            client: Client instance
            limit (int): Number of transactions to return
            offset (int): Offset for pagination
            status (str): Filter by status

        Returns:
            dict: Transaction history
        """
        try:
            queryset = Transaction.objects.filter(
                client=client,
                transaction_type='STK_PUSH'
            ).order_by('-created_at')

            if status:
                queryset = queryset.filter(status=status)

            total_count = queryset.count()
            transactions = queryset[offset:offset+limit]

            transaction_list = [
                self._format_transaction_status(transaction)
                for transaction in transactions
            ]

            return {
                'transactions': transaction_list,
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }

        except Exception as e:
            logger.error(f"Error getting transaction history: {e}")
            raise MPesaException(f"Failed to get transaction history: {e}")


# Service instance
stk_push_service = STKPushService()
