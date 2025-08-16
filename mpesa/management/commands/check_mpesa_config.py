"""
Management command to check M-Pesa configuration and identify potential issues.
This command helps diagnose problems with callback URLs, credentials, and connectivity.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from mpesa.models import MpesaConfiguration, MpesaCredentials, Transaction
from mpesa.mpesa_client import get_mpesa_client
from clients.models import Client
import requests
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check M-Pesa configuration and identify potential issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--client-id',
            type=str,
            help='Check configuration for specific client ID'
        )
        parser.add_argument(
            '--test-callback',
            action='store_true',
            help='Test if callback URL is accessible'
        )

    def handle(self, *args, **options):
        client_id = options.get('client_id')
        test_callback = options['test_callback']

        self.stdout.write(
            self.style.SUCCESS('=== M-Pesa Configuration Check ===\n')
        )

        # Check global configuration
        self._check_global_config()

        # Check database configuration
        self._check_database_config()

        # Check clients and credentials
        if client_id:
            self._check_specific_client(client_id)
        else:
            self._check_all_clients()

        # Test callback URL accessibility
        if test_callback:
            self._test_callback_url()

        # Check recent transactions
        self._check_recent_transactions()

        self.stdout.write(
            self.style.SUCCESS('\n=== Configuration Check Complete ===')
        )

    def _check_global_config(self):
        """Check global M-Pesa configuration from settings."""
        self.stdout.write(self.style.WARNING('1. Global Configuration (settings.py)'))

        mpesa_config = getattr(settings, 'MPESA_CONFIG', {})

        if not mpesa_config:
            self.stdout.write(
                self.style.ERROR('   ❌ MPESA_CONFIG not found in settings')
            )
            return

        required_fields = [
            'ENVIRONMENT', 'STK_CALLBACK_URL', 'VALIDATION_URL', 'CONFIRMATION_URL'
        ]

        for field in required_fields:
            value = mpesa_config.get(field, 'NOT SET')
            status = '✅' if value != 'NOT SET' else '❌'
            self.stdout.write(f'   {status} {field}: {value}')

        self.stdout.write('')

    def _check_database_config(self):
        """Check M-Pesa configuration in database."""
        self.stdout.write(self.style.WARNING('2. Database Configuration'))

        try:
            config = MpesaConfiguration.get_config()
            self.stdout.write(f'   ✅ STK Callback URL: {config.stk_callback_url}')
            self.stdout.write(f'   ✅ Validation URL: {config.validation_url}')
            self.stdout.write(f'   ✅ Confirmation URL: {config.confirmation_url}')
            self.stdout.write(f'   ✅ STK Timeout: {config.stk_timeout_seconds}s')
            self.stdout.write(f'   ✅ API Timeout: {config.api_timeout_seconds}s')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'   ❌ Database config error: {e}')
            )

        self.stdout.write('')

    def _check_all_clients(self):
        """Check all clients and their M-Pesa credentials."""
        self.stdout.write(self.style.WARNING('3. Client Credentials Overview'))

        clients = Client.objects.all()

        if not clients.exists():
            self.stdout.write(self.style.ERROR('   ❌ No clients found'))
            return

        for client in clients:
            sandbox_creds = MpesaCredentials.objects.filter(
                client=client, environment='sandbox', is_active=True
            ).first()

            live_creds = MpesaCredentials.objects.filter(
                client=client, environment='live', is_active=True
            ).first()

            sandbox_status = '✅' if sandbox_creds else '❌'
            live_status = '✅' if live_creds else '❌'

            self.stdout.write(
                f'   Client: {client.name} ({client.client_id})'
            )
            self.stdout.write(f'     {sandbox_status} Sandbox credentials')
            self.stdout.write(f'     {live_status} Live credentials')

        self.stdout.write('')

    def _check_specific_client(self, client_id):
        """Check specific client configuration in detail."""
        self.stdout.write(
            self.style.WARNING(f'3. Client Configuration: {client_id}')
        )

        try:
            client = Client.objects.get(client_id=client_id)
        except Client.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'   ❌ Client {client_id} not found')
            )
            return

        self.stdout.write(f'   Client Name: {client.name}')
        self.stdout.write(f'   Client ID: {client.client_id}')
        self.stdout.write(f'   Active: {client.is_active}')

        # Check credentials for both environments
        for env in ['sandbox', 'live']:
            self.stdout.write(f'\n   {env.upper()} Credentials:')

            creds = MpesaCredentials.objects.filter(
                client=client, environment=env, is_active=True
            ).first()

            if not creds:
                self.stdout.write(f'     ❌ No active {env} credentials')
                continue

            self.stdout.write(f'     ✅ Name: {creds.name}')
            self.stdout.write(f'     ✅ Business Shortcode: {creds.business_shortcode}')
            self.stdout.write(f'     ✅ Initiator Name: {creds.initiator_name}')
            self.stdout.write(f'     ✅ Base URL: {creds.base_url}')

            # Test credentials
            try:
                mpesa_client = get_mpesa_client(env, client)
                test_result = mpesa_client.test_connection()
                self.stdout.write(f'     ✅ Connection test: PASSED')
            except Exception as e:
                self.stdout.write(f'     ❌ Connection test: FAILED - {e}')

        self.stdout.write('')

    def _test_callback_url(self):
        """Test if callback URL is accessible."""
        self.stdout.write(self.style.WARNING('4. Callback URL Accessibility Test'))

        config = MpesaConfiguration.get_config()
        callback_url = config.stk_callback_url

        try:
            # Try to make a GET request to the callback URL
            response = requests.get(callback_url, timeout=10)

            if response.status_code == 405:  # Method not allowed is expected for POST endpoint
                self.stdout.write(f'   ✅ Callback URL is accessible: {callback_url}')
                self.stdout.write(f'     Status: {response.status_code} (Method Not Allowed - Expected)')
            elif response.status_code < 500:
                self.stdout.write(f'   ✅ Callback URL is accessible: {callback_url}')
                self.stdout.write(f'     Status: {response.status_code}')
            else:
                self.stdout.write(f'   ❌ Callback URL error: {callback_url}')
                self.stdout.write(f'     Status: {response.status_code}')

        except requests.exceptions.ConnectionError:
            self.stdout.write(f'   ❌ Callback URL not accessible: {callback_url}')
            self.stdout.write('     Connection error - M-Pesa cannot reach this URL')
        except requests.exceptions.Timeout:
            self.stdout.write(f'   ❌ Callback URL timeout: {callback_url}')
            self.stdout.write('     Timeout - URL takes too long to respond')
        except Exception as e:
            self.stdout.write(f'   ❌ Callback URL test failed: {e}')

        self.stdout.write('')

    def _check_recent_transactions(self):
        """Check recent transaction patterns."""
        self.stdout.write(self.style.WARNING('5. Recent Transaction Analysis'))

        from django.utils import timezone
        from datetime import timedelta

        # Get transactions from last 24 hours
        since = timezone.now() - timedelta(hours=24)
        recent_transactions = Transaction.objects.filter(
            created_at__gte=since,
            transaction_type='STK_PUSH'
        )

        total_count = recent_transactions.count()
        successful_count = recent_transactions.filter(status='SUCCESSFUL').count()
        failed_count = recent_transactions.filter(status='FAILED').count()
        processing_count = recent_transactions.filter(status='PROCESSING').count()
        callback_received_count = recent_transactions.filter(callback_received=True).count()

        self.stdout.write(f'   Last 24 hours:')
        self.stdout.write(f'     Total transactions: {total_count}')
        self.stdout.write(f'     Successful: {successful_count}')
        self.stdout.write(f'     Failed: {failed_count}')
        self.stdout.write(f'     Still processing: {processing_count}')
        self.stdout.write(f'     Callbacks received: {callback_received_count}')

        if total_count > 0:
            success_rate = (successful_count / total_count) * 100
            callback_rate = (callback_received_count / total_count) * 100

            self.stdout.write(f'     Success rate: {success_rate:.1f}%')
            self.stdout.write(f'     Callback rate: {callback_rate:.1f}%')

            if callback_rate < 50:
                self.stdout.write(
                    self.style.ERROR(
                        '     ⚠️ Low callback rate - Check callback URL configuration'
                    )
                )

            if processing_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'     ⚠️ {processing_count} transactions still processing'
                    )
                )

        self.stdout.write('')
