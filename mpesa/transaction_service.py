"""
Transaction service for managing and querying MPesa transactions.
"""

from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from mpesa.models import Transaction, CallbackLog
from mpesa.services.mpesa_client import get_mpesa_client
from core.exceptions import MPesaException, ValidationException
import logging

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Service for managing MPesa transactions.
    """

    def __init__(self, environment='sandbox'):
        """
        Initialize transaction service.

        Args:
            environment (str): 'sandbox' or 'live'
        """
        self.environment = environment
        self.client = get_mpesa_client(environment)

    def get_transaction(self, transaction_id, client=None):
        """
        Get transaction by ID.

        Args:
            transaction_id (str): Transaction ID
            client: Optional client for authorization

        Returns:
            dict: Transaction details
        """
        try:
            queryset = Transaction.objects.all()

            # Filter by client if provided (for authorization)
            if client:
                queryset = queryset.filter(client=client)

            transaction = queryset.get(transaction_id=transaction_id)

            return self._format_transaction(transaction)

        except Transaction.DoesNotExist:
            raise ValidationException(f"Transaction not found: {transaction_id}")
        except Exception as e:
            logger.error(f"Error getting transaction {transaction_id}: {e}")
            raise MPesaException(f"Failed to get transaction: {e}")

    def search_transactions(self, client=None, filters=None, page=1, page_size=20):
        """
        Search transactions with filters.

        Args:
            client: Optional client for filtering
            filters (dict): Search filters
            page (int): Page number
            page_size (int): Number of items per page

        Returns:
            dict: Search results with pagination
        """
        try:
            queryset = Transaction.objects.all().order_by('-created_at')

            # Filter by client if provided
            if client:
                queryset = queryset.filter(client=client)

            # Apply filters
            if filters:
                queryset = self._apply_filters(queryset, filters)

            # Paginate results
            paginator = Paginator(queryset, page_size)
            page_obj = paginator.get_page(page)

            transactions = [
                self._format_transaction(transaction)
                for transaction in page_obj.object_list
            ]

            return {
                'transactions': transactions,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_pages': paginator.num_pages,
                    'total_count': paginator.count,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                }
            }

        except Exception as e:
            logger.error(f"Error searching transactions: {e}")
            raise MPesaException(f"Failed to search transactions: {e}")

    def _apply_filters(self, queryset, filters):
        """Apply search filters to queryset."""
        try:
            # Status filter
            if filters.get('status'):
                queryset = queryset.filter(status=filters['status'])

            # Transaction type filter
            if filters.get('transaction_type'):
                queryset = queryset.filter(transaction_type=filters['transaction_type'])

            # Phone number filter
            if filters.get('phone_number'):
                queryset = queryset.filter(phone_number__contains=filters['phone_number'])

            # Amount range filter
            if filters.get('min_amount'):
                queryset = queryset.filter(amount__gte=filters['min_amount'])

            if filters.get('max_amount'):
                queryset = queryset.filter(amount__lte=filters['max_amount'])

            # Date range filter
            if filters.get('start_date'):
                start_date = datetime.fromisoformat(filters['start_date'].replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__gte=start_date)

            if filters.get('end_date'):
                end_date = datetime.fromisoformat(filters['end_date'].replace('Z', '+00:00'))
                queryset = queryset.filter(created_at__lte=end_date)

            # MPesa receipt number filter
            if filters.get('mpesa_receipt_number'):
                queryset = queryset.filter(mpesa_receipt_number=filters['mpesa_receipt_number'])

            # Reference filter
            if filters.get('reference'):
                queryset = queryset.filter(reference__icontains=filters['reference'])

            # Text search (across multiple fields)
            if filters.get('search'):
                search_term = filters['search']
                queryset = queryset.filter(
                    Q(description__icontains=search_term) |
                    Q(reference__icontains=search_term) |
                    Q(mpesa_receipt_number__icontains=search_term) |
                    Q(phone_number__icontains=search_term)
                )

            return queryset

        except Exception as e:
            logger.error(f"Error applying filters: {e}")
            raise ValidationException(f"Invalid filter parameters: {e}")

    def get_transaction_statistics(self, client=None, period='today'):
        """
        Get transaction statistics.

        Args:
            client: Optional client for filtering
            period (str): Time period ('today', 'week', 'month', 'year')

        Returns:
            dict: Transaction statistics
        """
        try:
            queryset = Transaction.objects.all()

            # Filter by client if provided
            if client:
                queryset = queryset.filter(client=client)

            # Apply time period filter
            end_date = timezone.now()

            if period == 'today':
                start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == 'week':
                start_date = end_date - timedelta(days=7)
            elif period == 'month':
                start_date = end_date - timedelta(days=30)
            elif period == 'year':
                start_date = end_date - timedelta(days=365)
            else:
                start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

            period_queryset = queryset.filter(created_at__gte=start_date)

            # Calculate statistics
            stats = {
                'period': period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_transactions': period_queryset.count(),
                'successful_transactions': period_queryset.filter(status='SUCCESSFUL').count(),
                'failed_transactions': period_queryset.filter(status='FAILED').count(),
                'pending_transactions': period_queryset.filter(status='PENDING').count(),
                'total_amount': float(period_queryset.filter(status='SUCCESSFUL').aggregate(
                    total=Sum('amount'))['total'] or 0),
                'average_amount': 0,
                'transaction_types': {},
                'status_breakdown': {},
                'daily_breakdown': []
            }

            # Calculate average amount
            if stats['successful_transactions'] > 0:
                stats['average_amount'] = stats['total_amount'] / stats['successful_transactions']

            # Transaction type breakdown
            type_stats = period_queryset.values('transaction_type').annotate(
                count=Count('transaction_id'),
                total_amount=Sum('amount')
            )

            for type_stat in type_stats:
                stats['transaction_types'][type_stat['transaction_type']] = {
                    'count': type_stat['count'],
                    'total_amount': float(type_stat['total_amount'] or 0)
                }

            # Status breakdown
            status_stats = period_queryset.values('status').annotate(count=Count('transaction_id'))

            for status_stat in status_stats:
                stats['status_breakdown'][status_stat['status']] = status_stat['count']

            # Daily breakdown for longer periods
            if period in ['week', 'month', 'year']:
                daily_stats = self._get_daily_breakdown(period_queryset, start_date, end_date)
                stats['daily_breakdown'] = daily_stats

            return stats

        except Exception as e:
            logger.error(f"Error getting transaction statistics: {e}")
            raise MPesaException(f"Failed to get statistics: {e}")

    def _get_daily_breakdown(self, queryset, start_date, end_date):
        """Get daily breakdown of transactions."""
        try:
            daily_stats = []
            current_date = start_date.date()
            end_date_only = end_date.date()

            while current_date <= end_date_only:
                day_start = timezone.make_aware(datetime.combine(current_date, datetime.min.time()))
                day_end = day_start + timedelta(days=1) - timedelta(microseconds=1)

                day_queryset = queryset.filter(
                    created_at__gte=day_start,
                    created_at__lte=day_end
                )

                daily_stat = {
                    'date': current_date.isoformat(),
                    'total_transactions': day_queryset.count(),
                    'successful_transactions': day_queryset.filter(status='SUCCESSFUL').count(),
                    'total_amount': float(day_queryset.filter(status='SUCCESSFUL').aggregate(
                        total=Sum('amount'))['total'] or 0)
                }

                daily_stats.append(daily_stat)
                current_date += timedelta(days=1)

            return daily_stats

        except Exception as e:
            logger.error(f"Error getting daily breakdown: {e}")
            return []

    def validate_offline_payment(self, mpesa_receipt_number, client=None):
        """
        Validate offline MPesa payment.

        Args:
            mpesa_receipt_number (str): MPesa receipt number
            client: Optional client for authorization

        Returns:
            dict: Validation result
        """
        try:
            # Check if transaction already exists
            existing_transaction = Transaction.objects.filter(
                mpesa_receipt_number=mpesa_receipt_number
            ).first()

            if existing_transaction:
                return {
                    'status': 'exists',
                    'message': 'Transaction already recorded',
                    'transaction': self._format_transaction(existing_transaction)
                }

            # Query MPesa for transaction details
            # Note: This would require a transaction status API call to MPesa
            # For now, we'll return a placeholder response

            return {
                'status': 'not_found',
                'message': 'Transaction not found in our records',
                'mpesa_receipt_number': mpesa_receipt_number
            }

        except Exception as e:
            logger.error(f"Error validating offline payment {mpesa_receipt_number}: {e}")
            raise MPesaException(f"Failed to validate payment: {e}")

    def retry_failed_transaction(self, transaction_id, client=None):
        """
        Retry a failed transaction.

        Args:
            transaction_id (str): Transaction ID to retry
            client: Optional client for authorization

        Returns:
            dict: Retry result
        """
        try:
            queryset = Transaction.objects.all()

            if client:
                queryset = queryset.filter(client=client)

            transaction = queryset.get(transaction_id=transaction_id)

            if transaction.status != 'FAILED':
                raise ValidationException(f"Cannot retry transaction with status: {transaction.status}")

            if transaction.transaction_type != 'STK_PUSH':
                raise ValidationException("Only STK Push transactions can be retried")

            # Import here to avoid circular imports
            from mpesa.services.stk_push_service import STKPushService

            # Create new STK push with same details
            stk_service = STKPushService(self.environment)

            result = stk_service.initiate_stk_push(
                client=transaction.client,
                phone_number=transaction.phone_number,
                amount=transaction.amount,
                description=transaction.description,
                reference=f"RETRY_{transaction.reference}"
            )

            return {
                'status': 'retry_initiated',
                'message': 'New payment request sent',
                'original_transaction_id': str(transaction.transaction_id),
                'new_transaction_id': result['transaction_id']
            }

        except Transaction.DoesNotExist:
            raise ValidationException(f"Transaction not found: {transaction_id}")
        except Exception as e:
            logger.error(f"Error retrying transaction {transaction_id}: {e}")
            raise MPesaException(f"Failed to retry transaction: {e}")

    def export_transactions(self, client=None, filters=None, format='csv'):
        """
        Export transactions to file.

        Args:
            client: Optional client for filtering
            filters (dict): Export filters
            format (str): Export format ('csv', 'json', 'excel')

        Returns:
            dict: Export result with download URL or data
        """
        try:
            queryset = Transaction.objects.all().order_by('-created_at')

            if client:
                queryset = queryset.filter(client=client)

            if filters:
                queryset = self._apply_filters(queryset, filters)

            # Limit export size for performance
            if queryset.count() > 10000:
                raise ValidationException("Export limited to 10,000 transactions. Please use filters to reduce the dataset.")

            transactions = list(queryset)

            if format == 'csv':
                return self._export_to_csv(transactions)
            elif format == 'json':
                return self._export_to_json(transactions)
            elif format == 'excel':
                return self._export_to_excel(transactions)
            else:
                raise ValidationException(f"Unsupported export format: {format}")

        except Exception as e:
            logger.error(f"Error exporting transactions: {e}")
            raise MPesaException(f"Failed to export transactions: {e}")

    def _export_to_csv(self, transactions):
        """Export transactions to CSV format."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Transaction ID', 'Client', 'Type', 'Phone Number', 'Amount',
            'Description', 'Reference', 'Status', 'MPesa Receipt',
            'Created At', 'Updated At'
        ])

        # Write data
        for transaction in transactions:
            writer.writerow([
                str(transaction.transaction_id),
                transaction.client.name if transaction.client else '',
                transaction.transaction_type,
                transaction.phone_number,
                float(transaction.amount),
                transaction.description,
                transaction.reference,
                transaction.status,
                transaction.mpesa_receipt_number or '',
                transaction.created_at.isoformat(),
                transaction.updated_at.isoformat()
            ])

        return {
            'format': 'csv',
            'data': output.getvalue(),
            'filename': f'transactions_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv'
        }

    def _export_to_json(self, transactions):
        """Export transactions to JSON format."""
        import json

        data = [self._format_transaction(transaction) for transaction in transactions]

        return {
            'format': 'json',
            'data': json.dumps(data, indent=2),
            'filename': f'transactions_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
        }

    def _export_to_excel(self, transactions):
        """Export transactions to Excel format."""
        # This would require openpyxl or xlsxwriter
        # For now, return CSV format
        return self._export_to_csv(transactions)

    def _format_transaction(self, transaction):
        """Format transaction for API response."""
        return {
            'transaction_id': str(transaction.transaction_id),
            'client_id': str(transaction.client.client_id) if transaction.client else None,
            'client_name': transaction.client.name if transaction.client else None,
            'transaction_type': transaction.transaction_type,
            'phone_number': transaction.phone_number,
            'amount': float(transaction.amount),
            'description': transaction.description,
            'reference': transaction.reference,
            'status': transaction.status,
            'mpesa_receipt_number': transaction.mpesa_receipt_number,
            'mpesa_checkout_request_id': transaction.checkout_request_id,
            'response_code': transaction.response_code,
            'response_description': transaction.response_description,
            'callback_received': transaction.callback_received,
            'transaction_date': transaction.transaction_date.isoformat() if transaction.transaction_date else None,
            'created_at': transaction.created_at.isoformat(),
            'updated_at': transaction.updated_at.isoformat()
        }


# Service instance
transaction_service = TransactionService()
