"""
Callback service for processing MPesa payment callbacks and notifications.
"""

import json
from datetime import datetime
from django.utils import timezone
from django.http import HttpResponse
from mpesa.models import Transaction, CallbackLog
from core.exceptions import MPesaException
import logging

logger = logging.getLogger(__name__)


class CallbackService:
    """
    Service for handling MPesa callbacks and notifications.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_stk_callback(self, request_data, ip_address=None, user_agent=None, headers=None, callback_log=None):
        """
        Process STK Push callback from MPesa.

        Args:
            request_data (dict): Callback data from MPesa
            ip_address (str): Source IP address
            user_agent (str): User agent
            headers (dict): HTTP headers
            callback_log (CallbackLog): Existing callback log to use (optional)

        Returns:
            dict: Processing result
        """
        try:
            # Use existing callback log or create new one
            if callback_log is None:
                callback_log = self._log_callback(
                    callback_type='STK_PUSH',
                    raw_data=request_data,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    headers=headers or {}
                )

            logger.info(f"Received STK callback from IP: {ip_address}")
            logger.info(f"Callback data: {request_data}")

            # Validate callback structure
            if not self._validate_stk_callback(request_data):
                error_msg = "Invalid STK callback structure"
                logger.error(f"Callback validation failed: {error_msg}")
                logger.error(f"Raw callback data: {request_data}")
                self._mark_callback_failed(callback_log, error_msg)
                return {'status': 'error', 'message': error_msg}

            # Extract callback data
            stk_callback = request_data['Body']['stkCallback']
            checkout_request_id = stk_callback.get('CheckoutRequestID')

            if not checkout_request_id:
                error_msg = "Missing CheckoutRequestID in callback"
                logger.error(f"Callback missing checkout request ID: {stk_callback}")
                self._mark_callback_failed(callback_log, error_msg)
                return {'status': 'error', 'message': error_msg}

            logger.info(f"Processing callback for CheckoutRequestID: {checkout_request_id}")

            # Find transaction
            transaction = Transaction.objects.get_transaction_by_checkout_request_id(checkout_request_id)

            if not transaction:
                error_msg = f"Transaction not found for CheckoutRequestID: {checkout_request_id}"
                logger.warning(error_msg)
                logger.warning(f"Available transactions: {Transaction.objects.filter(checkout_request_id__isnull=False).values_list('checkout_request_id', flat=True)[:10]}")
                self._mark_callback_failed(callback_log, error_msg)
                # Return success to avoid MPesa retries for unknown transactions
                return {'status': 'success', 'message': 'Transaction not found but acknowledged'}

            logger.info(f"Found transaction: {transaction.transaction_id} for client: {transaction.client.name}")

            # Link callback to transaction
            callback_log.transaction = transaction
            callback_log.save()

            # Process the callback
            self._process_stk_callback_data(transaction, stk_callback)

            # Mark callback as processed
            callback_log.mark_as_processed(success=True)

            # Send notifications if needed
            self._send_notifications(transaction)

            logger.info(f"STK callback processed successfully for transaction: {transaction.transaction_id}")

            return {
                'status': 'success',
                'message': 'Callback processed successfully',
                'transaction_id': str(transaction.transaction_id)
            }

        except Transaction.DoesNotExist:
            error_msg = f"Transaction not found for checkout request ID: {checkout_request_id}"
            logger.warning(error_msg)
            self._mark_callback_failed(callback_log, error_msg)
            return {'status': 'success', 'message': 'Transaction not found but acknowledged'}

        except Exception as e:
            error_msg = f"Error processing STK callback: {e}"
            logger.error(error_msg)
            logger.exception("Full callback processing error traceback:")
            self._mark_callback_failed(callback_log, error_msg)
            return {'status': 'error', 'message': 'Callback processing failed'}

    def process_c2b_validation(self, request_data, ip_address=None, user_agent=None, headers=None):
        """
        Process C2B validation request.

        Args:
            request_data (dict): Validation data from MPesa
            ip_address (str): Source IP address
            user_agent (str): User agent
            headers (dict): HTTP headers

        Returns:
            dict: Validation result
        """
        callback_log = None

        try:
            # Log the callback
            callback_log = self._log_callback(
                callback_type='C2B_VALIDATION',
                raw_data=request_data,
                ip_address=ip_address,
                user_agent=user_agent,
                headers=headers or {}
            )

            # Extract validation data
            trans_type = request_data.get('TransType')
            trans_id = request_data.get('TransID')
            trans_time = request_data.get('TransTime')
            trans_amount = request_data.get('TransAmount')
            business_short_code = request_data.get('BusinessShortCode')
            bill_ref_number = request_data.get('BillRefNumber')
            invoice_number = request_data.get('InvoiceNumber')
            org_account_balance = request_data.get('OrgAccountBalance')
            third_party_trans_id = request_data.get('ThirdPartyTransID')
            msisdn = request_data.get('MSISDN')
            first_name = request_data.get('FirstName')
            middle_name = request_data.get('MiddleName')
            last_name = request_data.get('LastName')

            # Validate the transaction
            validation_result = self._validate_c2b_transaction(request_data)

            # Mark callback as processed
            callback_log.mark_as_processed(success=True)

            logger.info(f"C2B validation processed: {trans_id}")

            return validation_result

        except Exception as e:
            error_msg = f"Error processing C2B validation: {e}"
            self._mark_callback_failed(callback_log, error_msg)
            logger.error(error_msg)
            return {
                'ResultCode': '1',
                'ResultDesc': 'Validation failed'
            }

    def process_c2b_confirmation(self, request_data, ip_address=None, user_agent=None, headers=None):
        """
        Process C2B confirmation request.

        Args:
            request_data (dict): Confirmation data from MPesa
            ip_address (str): Source IP address
            user_agent (str): User agent
            headers (dict): HTTP headers

        Returns:
            dict: Confirmation result
        """
        callback_log = None

        try:
            # Log the callback
            callback_log = self._log_callback(
                callback_type='C2B_CONFIRMATION',
                raw_data=request_data,
                ip_address=ip_address,
                user_agent=user_agent,
                headers=headers or {}
            )

            # Create transaction record for C2B payment
            transaction = self._create_c2b_transaction(request_data)

            if transaction:
                callback_log.transaction = transaction
                callback_log.save()

                # Send notifications
                self._send_notifications(transaction)

            # Mark callback as processed
            callback_log.mark_as_processed(success=True)

            logger.info(f"C2B confirmation processed: {request_data.get('TransID')}")

            return {
                'ResultCode': '0',
                'ResultDesc': 'Success'
            }

        except Exception as e:
            error_msg = f"Error processing C2B confirmation: {e}"
            self._mark_callback_failed(callback_log, error_msg)
            logger.error(error_msg)
            return {
                'ResultCode': '1',
                'ResultDesc': 'Confirmation failed'
            }

    def _validate_stk_callback(self, data):
        """Validate STK callback structure."""
        try:
            return (
                'Body' in data and
                'stkCallback' in data['Body'] and
                'CheckoutRequestID' in data['Body']['stkCallback']
            )
        except Exception:
            return False

    def _process_stk_callback_data(self, transaction, stk_callback):
        """Process STK callback data and update transaction."""
        try:
            # Update transaction with callback data
            transaction.process_callback({'Body': {'stkCallback': stk_callback}})

            logger.info(f"Transaction {transaction.transaction_id} updated with callback data")

        except Exception as e:
            logger.error(f"Error processing callback data for {transaction.transaction_id}: {e}")
            raise

    def _validate_c2b_transaction(self, data):
        """Validate C2B transaction."""
        try:
            # Basic validation - can be customized based on business rules
            trans_amount = float(data.get('TransAmount', 0))

            if trans_amount < 1:
                return {
                    'ResultCode': '1',
                    'ResultDesc': 'Minimum amount is KES 1'
                }

            if trans_amount > 150000:
                return {
                    'ResultCode': '1',
                    'ResultDesc': 'Maximum amount is KES 150,000'
                }

            # Add more validation rules as needed

            return {
                'ResultCode': '0',
                'ResultDesc': 'Success'
            }

        except Exception as e:
            logger.error(f"Error validating C2B transaction: {e}")
            return {
                'ResultCode': '1',
                'ResultDesc': 'Validation error'
            }

    def _create_c2b_transaction(self, data):
        """Create transaction record for C2B payment."""
        try:
            from core.utils.phone import format_phone_for_mpesa

            # Extract data
            trans_type = data.get('TransType', '')
            trans_id = data.get('TransID', '')
            trans_amount = float(data.get('TransAmount', 0))
            msisdn = data.get('MSISDN', '')
            bill_ref_number = data.get('BillRefNumber', '')

            # Determine transaction type
            if trans_type == 'Pay Bill':
                transaction_type = 'C2B_PAYBILL'
            elif trans_type == 'Buy Goods':
                transaction_type = 'C2B_BUYGOODS'
            else:
                transaction_type = 'C2B_PAYBILL'  # default

            # Format phone number
            try:
                formatted_phone = format_phone_for_mpesa(msisdn)
            except Exception:
                formatted_phone = msisdn

            # For C2B, we need to determine the client based on business shortcode
            # For now, we'll use the default client ID as transactions require a client
            from clients.models import Client

            try:
                # Try to find client by shortcode or use default
                default_client = Client.objects.get(client_id='79e8dc5bf9544264917f74a7f55c05ab')
            except Client.DoesNotExist:
                logger.error("Default client not found for C2B transaction")
                return None

            # Create transaction
            transaction = Transaction.objects.create(
                client=default_client,
                transaction_type=transaction_type,
                phone_number=formatted_phone,
                amount=trans_amount,
                description=f"C2B Payment - {bill_ref_number}" if bill_ref_number else "C2B Payment",
                reference=bill_ref_number or trans_id,
                mpesa_receipt_number=trans_id,
                status='SUCCESSFUL',
                response_code='0',
                response_description='C2B payment received',
                callback_received=True,
                callback_data=data,
                transaction_date=timezone.now()
            )

            logger.info(f"Created C2B transaction: {transaction.transaction_id}")
            return transaction

        except Exception as e:
            logger.error(f"Error creating C2B transaction: {e}")
            return None

    def _log_callback(self, callback_type, raw_data, ip_address=None, user_agent=None, headers=None):
        """Log callback for audit purposes."""
        try:
            return CallbackLog.objects.create(
                callback_type=callback_type,
                ip_address=ip_address or '0.0.0.0',
                user_agent=user_agent or '',
                headers=headers or {},
                raw_data=raw_data
            )
        except Exception as e:
            logger.error(f"Error logging callback: {e}")
            return None

    def _mark_callback_failed(self, callback_log, error_message):
        """Mark callback as failed."""
        if callback_log:
            try:
                callback_log.mark_as_processed(success=False, error_message=error_message)
            except Exception as e:
                logger.error(f"Error marking callback as failed: {e}")

    def _send_notifications(self, transaction):
        """Send notifications for transaction updates."""
        try:
            # Send webhook notification
            if transaction.client and transaction.client.webhook_url:
                self._send_webhook_notification(transaction)

            # Send email and WhatsApp notifications based on transaction status
            if transaction.client:
                try:
                    if transaction.is_successful():
                        from core.utils.notification_service import notify_payment_received
                        notify_payment_received(transaction.client, transaction)
                    elif transaction.is_failed():
                        from core.utils.notification_service import notify_payment_failed
                        notify_payment_failed(transaction.client, transaction)
                except Exception as e:
                    logger.warning(f"Failed to send email/WhatsApp notifications: {e}")

        except Exception as e:
            logger.error(f"Error sending notifications for {transaction.transaction_id}: {e}")

    def _send_webhook_notification(self, transaction):
        """Send webhook notification to client."""
        try:
            import requests
            import hmac
            import hashlib

            webhook_url = transaction.client.webhook_url
            if not webhook_url:
                return

            # Prepare webhook payload
            payload = {
                'event': 'transaction.updated',
                'transaction_id': str(transaction.transaction_id),
                'mpesa_receipt_number': transaction.mpesa_receipt_number,
                'phone_number': transaction.phone_number,
                'amount': float(transaction.amount),
                'status': transaction.status,
                'description': transaction.description,
                'reference': transaction.reference,
                'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
                'updated_at': transaction.updated_at.isoformat()
            }

            # Create signature if webhook secret is configured
            headers = {'Content-Type': 'application/json'}

            if transaction.client.webhook_secret:
                payload_json = json.dumps(payload, sort_keys=True)
                signature = hmac.new(
                    transaction.client.webhook_secret.encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers['X-Signature'] = signature

            # Send webhook
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.ok:
                logger.info(f"Webhook sent successfully for transaction {transaction.transaction_id}")
            else:
                logger.warning(f"Webhook failed for transaction {transaction.transaction_id}: {response.status_code}")

        except Exception as e:
            logger.error(f"Error sending webhook for transaction {transaction.transaction_id}: {e}")

    def get_callback_logs(self, limit=50, offset=0, callback_type=None):
        """
        Get callback logs for monitoring.

        Args:
            limit (int): Number of logs to return
            offset (int): Offset for pagination
            callback_type (str): Filter by callback type

        Returns:
            dict: Callback logs
        """
        try:
            queryset = CallbackLog.objects.all().order_by('-received_at')

            if callback_type:
                queryset = queryset.filter(callback_type=callback_type)

            total_count = queryset.count()
            logs = queryset[offset:offset+limit]

            log_list = []
            for log in logs:
                log_data = {
                    'log_id': str(log.log_id),
                    'callback_type': log.callback_type,
                    'ip_address': log.ip_address,
                    'processed_successfully': log.processed_successfully,
                    'error_message': log.error_message,
                    'received_at': log.received_at.isoformat(),
                    'processed_at': log.processed_at.isoformat() if log.processed_at else None
                }

                if log.transaction:
                    log_data['transaction_id'] = str(log.transaction.transaction_id)

                log_list.append(log_data)

            return {
                'logs': log_list,
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }

        except Exception as e:
            logger.error(f"Error getting callback logs: {e}")
            raise MPesaException(f"Failed to get callback logs: {e}")


# Service instance - use lazy initialization to avoid database access during import
# callback_service = CallbackService()  # Removed to prevent database access during import

def get_callback_service():
    """Get Callback service instance (lazy initialization)."""
    global _callback_service
    if '_callback_service' not in globals():
        global _callback_service
        _callback_service = CallbackService()
    return _callback_service
