"""
STK Push service for initiating MPesa payment requests.
"""

import uuid
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from mpesa.models import Transaction, MpesaConfiguration
from mpesa.mpesa_client import get_mpesa_client
from core.exceptions import MPesaException, ValidationException
from core.utils.phone import normalize_phone_number, PhoneNumberError
import logging

logger = logging.getLogger(__name__)


class STKPushService:
    """
    Service for handling STK Push (Lipa na M-Pesa Online) transactions.
    """

    def __init__(self, environment=None, client=None):
        """
        Initialize STK Push service.

        Args:
            environment (str): 'sandbox' or 'live' (defaults to settings)
            client: Client instance for accessing client-specific credentials
        """
        self.environment = environment or settings.MPESA_CONFIG.get('ENVIRONMENT', 'sandbox')
        self.client_instance = client
        self.client = get_mpesa_client(self.environment, client) if client else None
        self.config = MpesaConfiguration.get_config()

    def initiate_stk_push(self, client, phone_number, amount, description,
                         reference=None, account_reference=None,
                         ip_address=None, user_agent=None, callback_url=None):
        """
        Initiate STK Push payment request.

        Args:
            client: Client instance making the request
            phone_number (str): Customer phone number
            amount (decimal.Decimal): Payment amount
            description (str): Payment description
            reference (str): Optional transaction reference
            account_reference (str): Optional account reference shown to user
            ip_address (str): Client IP address
            user_agent (str): Client user agent
            callback_url (str): Optional custom callback URL

        Returns:
            dict: STK Push response with transaction details
        """
        try:
            # Initialize the MPesa client with the specific client if not already done
            if not self.client:
                self.client = get_mpesa_client(self.environment, client)

            # Validate inputs
            self._validate_stk_push_inputs(phone_number, amount, description)

            # Format phone number
            formatted_phone = normalize_phone_number(phone_number)

            # Generate reference if not provided
            if not reference:
                reference = f"TXN_{uuid.uuid4().hex[:8].upper()}"

            # Create transaction record
            transaction = Transaction.objects.create_stk_push_transaction(
                client=client,
                phone_number=formatted_phone,
                amount=amount,
                description=description,
                reference=reference
            )

            # Set additional fields
            if ip_address:
                transaction.ip_address = ip_address
            if user_agent:
                transaction.user_agent = user_agent
            transaction.save(update_fields=['ip_address', 'user_agent'])

            # Prepare STK Push request
            stk_request = self._prepare_stk_push_request(
                phone_number=formatted_phone,
                amount=amount,
                description=description,
                reference=account_reference or reference,
                callback_url=callback_url
            )

            # Make API request
            response = self.client.make_request('/mpesa/stkpush/v1/processrequest', stk_request)

            # Update transaction with response
            self._update_transaction_with_response(transaction, response)

            # Prepare response
            result = {
                'transaction_id': transaction.transaction_id,
                'checkout_request_id': response.get('CheckoutRequestID'),
                'merchant_request_id': response.get('MerchantRequestID'),
                'response_code': response.get('ResponseCode'),
                'response_description': response.get('ResponseDescription'),
                'customer_message': response.get('CustomerMessage'),
                'phone_number': formatted_phone,
                'amount': float(amount),
                'description': description,
                'reference': reference,
                'status': transaction.status,
                'created_at': transaction.created_at
            }

            logger.info(f"STK Push initiated successfully: {transaction.transaction_id}")
            return result

        except PhoneNumberError as e:
            logger.error(f"Invalid phone number for STK Push: {e}")
            raise ValidationException(f"Invalid phone number: {e}")
        except MPesaException:
            raise
        except Exception as e:
            logger.error(f"Error initiating STK Push: {e}")
            raise MPesaException(f"Failed to initiate payment: {e}")

    def _validate_stk_push_inputs(self, phone_number, amount, description):
        """Validate STK Push inputs."""
        if not phone_number:
            raise ValidationException("Phone number is required")

        if not amount or amount <= 0:
            raise ValidationException("Amount must be greater than 0")

        if amount < 1:
            raise ValidationException("Minimum amount is KES 1")

        if amount > 150000:  # MPesa limit
            raise ValidationException("Maximum amount is KES 150,000")

        if not description:
            raise ValidationException("Description is required")

        if len(description) > 255:
            raise ValidationException("Description too long (max 255 characters)")

    def _prepare_stk_push_request(self, phone_number, amount, description, reference, callback_url=None):
        """Prepare STK Push request data."""
        try:
            # Generate password and timestamp
            password, timestamp = self.client.generate_password()

            # Use configured callback URL or default
            callback_url = callback_url or self.config.stk_callback_url

            if not callback_url:
                callback_url = settings.MPESA_CONFIG.get('STK_CALLBACK_URL')
                if not callback_url:
                    raise ValidationException("No callback URL configured")

            # Prepare request data
            request_data = {
                "BusinessShortCode": self.client.get_business_shortcode(),
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(float(amount)),  # Convert to integer
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
            if not self.client_instance:
                raise ValidationException("Client instance is required for transaction queries")

            # Get transaction filtered by client
            if transaction_id:
                transaction = Transaction.objects.get(
                    transaction_id=transaction_id,
                    client=self.client_instance
                )
            elif checkout_request_id:
                transaction = Transaction.objects.get(
                    checkout_request_id=checkout_request_id,
                    client=self.client_instance
                )
            else:
                raise ValidationException("Either transaction_id or checkout_request_id is required")

            # If transaction is already completed, return cached status
            if transaction.status in ['SUCCESSFUL', 'FAILED', 'CANCELLED']:
                return self._format_transaction_status(transaction)

            # Query MPesa API for latest status if still processing and no callback received
            if transaction.status == 'PROCESSING' and not transaction.callback_received:
                # Check how long ago the transaction was created
                time_since_creation = timezone.now() - transaction.created_at

                # Only query API if transaction is more than 30 seconds old
                if time_since_creation.total_seconds() > 30:
                    status_response = self._query_mpesa_status(transaction)

                    if status_response:
                        # Update transaction with latest status
                        self._update_transaction_with_status_response(transaction, status_response)
                    else:
                        # If query fails and it's been more than 5 minutes, mark as failed
                        if time_since_creation.total_seconds() > 300:  # 5 minutes
                            transaction.update_status(
                                'FAILED',
                                response_description='Transaction timeout - no response from MPesa'
                            )

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
            'checkout_request_id': transaction.checkout_request_id,
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
            if not self.client_instance:
                raise ValidationException("Client instance is required for transaction operations")

            transaction = Transaction.objects.get(
                transaction_id=transaction_id,
                client=self.client_instance
            )

            if transaction.status not in ['PENDING', 'PROCESSING']:
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

    def get_transaction_summary(self, client, date_from=None, date_to=None):
        """
        Get transaction summary for a client.

        Args:
            client: Client instance
            date_from (datetime): Start date filter
            date_to (datetime): End date filter

        Returns:
            dict: Transaction summary
        """
        try:
            queryset = Transaction.objects.filter(
                client=client,
                transaction_type='STK_PUSH'
            )

            if date_from:
                queryset = queryset.filter(created_at__gte=date_from)
            if date_to:
                queryset = queryset.filter(created_at__lte=date_to)

            # Calculate summary statistics
            total_count = queryset.count()
            successful_count = queryset.filter(status='SUCCESSFUL').count()
            failed_count = queryset.filter(status='FAILED').count()
            pending_count = queryset.filter(status__in=['PENDING', 'PROCESSING']).count()

            total_amount = sum(
                float(t.amount) for t in queryset.filter(status='SUCCESSFUL')
            )

            return {
                'total_transactions': total_count,
                'successful_transactions': successful_count,
                'failed_transactions': failed_count,
                'pending_transactions': pending_count,
                'total_amount': total_amount,
                'success_rate': (successful_count / total_count * 100) if total_count > 0 else 0,
                'period': {
                    'from': date_from.isoformat() if date_from else None,
                    'to': date_to.isoformat() if date_to else None
                }
            }

        except Exception as e:
            logger.error(f"Error getting transaction summary: {e}")
            raise MPesaException(f"Failed to get transaction summary: {e}")

    def check_transaction_status_actively(self, transaction_id):
        """
        Actively check transaction status by querying M-Pesa API.
        This method should be called when callback is not received.

        Args:
            transaction_id (str): Transaction ID to check

        Returns:
            dict: Updated transaction status
        """
        try:
            if not self.client_instance:
                raise ValidationException("Client instance is required for transaction operations")

            transaction = Transaction.objects.get(
                transaction_id=transaction_id,
                client=self.client_instance
            )

            # Only check if transaction is still processing
            if transaction.status not in ['PROCESSING', 'PENDING']:
                return self._format_transaction_status(transaction)

            # Query M-Pesa API for current status
            status_response = self._query_mpesa_status(transaction)

            if status_response:
                self._update_transaction_with_status_response(transaction, status_response)
                logger.info(f"Transaction status updated via API query: {transaction.transaction_id}")
            else:
                logger.warning(f"Failed to query transaction status: {transaction.transaction_id}")

            return self._format_transaction_status(transaction)

        except Transaction.DoesNotExist:
            raise ValidationException("Transaction not found")
        except Exception as e:
            logger.error(f"Error in active status check: {e}")
            raise MPesaException(f"Failed to check transaction status: {e}")


# Service instance - use lazy initialization to avoid database access during import
# stk_push_service = STKPushService()  # Removed to prevent database access during import

def get_stk_push_service():
    """Get STK Push service instance (lazy initialization)."""
    global _stk_push_service
    if '_stk_push_service' not in globals():
        global _stk_push_service
        _stk_push_service = STKPushService()
    return _stk_push_service
