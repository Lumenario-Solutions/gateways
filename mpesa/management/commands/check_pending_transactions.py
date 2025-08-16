"""
Management command to check pending M-Pesa transactions and update their status.
This command should be run periodically (e.g., via cron) to ensure transaction
statuses are updated even if callbacks are not received.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from mpesa.models import Transaction
from mpesa.services.stk_push_service import STKPushService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check pending M-Pesa transactions and update their status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age',
            type=int,
            default=60,
            help='Maximum age in minutes for transactions to check (default: 60)'
        )
        parser.add_argument(
            '--min-age',
            type=int,
            default=1,
            help='Minimum age in minutes before checking transaction (default: 1)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of transactions to check (default: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be checked without making API calls'
        )

    def handle(self, *args, **options):
        max_age_minutes = options['max_age']
        min_age_minutes = options['min_age']
        limit = options['limit']
        dry_run = options['dry_run']

        # Calculate time boundaries
        now = timezone.now()
        max_age = now - timedelta(minutes=max_age_minutes)
        min_age = now - timedelta(minutes=min_age_minutes)

        # Find pending transactions to check
        pending_transactions = Transaction.objects.filter(
            status='PROCESSING',
            callback_received=False,
            created_at__gte=max_age,
            created_at__lte=min_age,
            transaction_type='STK_PUSH'
        ).order_by('created_at')[:limit]

        total_found = pending_transactions.count()

        if total_found == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'No pending transactions found between {min_age_minutes} and {max_age_minutes} minutes old'
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f'Found {total_found} pending transactions to check'
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No API calls will be made'))
            for transaction in pending_transactions:
                age_minutes = (now - transaction.created_at).total_seconds() / 60
                self.stdout.write(
                    f'Would check: {transaction.transaction_id} '
                    f'(Client: {transaction.client.name}, Age: {age_minutes:.1f}m)'
                )
            return

        checked_count = 0
        updated_count = 0
        failed_count = 0

        for transaction in pending_transactions:
            try:
                # Initialize service with the transaction's client
                stk_service = STKPushService(client=transaction.client)

                # Get current status before checking
                old_status = transaction.status

                # Check transaction status
                result = stk_service.check_transaction_status_actively(
                    str(transaction.transaction_id)
                )

                # Refresh transaction from database to get updated status
                transaction.refresh_from_db()
                new_status = transaction.status

                checked_count += 1

                if old_status != new_status:
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated: {transaction.transaction_id} '
                            f'{old_status} -> {new_status}'
                        )
                    )
                else:
                    self.stdout.write(
                        f'No change: {transaction.transaction_id} '
                        f'(Status: {new_status})'
                    )

            except Exception as e:
                failed_count += 1
                logger.error(f'Failed to check transaction {transaction.transaction_id}: {e}')
                self.stdout.write(
                    self.style.ERROR(
                        f'Failed: {transaction.transaction_id} - {str(e)}'
                    )
                )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'  Transactions checked: {checked_count}\n'
                f'  Status updated: {updated_count}\n'
                f'  Failed: {failed_count}'
            )
        )

        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated {updated_count} transaction statuses'
                )
            )
