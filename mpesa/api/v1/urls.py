"""
MPesa API v1 URL patterns.
"""

from django.urls import path
from . import views

app_name = 'mpesa_v1'

urlpatterns = [
    # STK Push endpoints
    path('initiate/', views.STKPushInitiateView.as_view(), name='stk-push-initiate'),
    path('callback/', views.MPesaCallbackView.as_view(), name='mpesa-callback'),
    path('status/<uuid:transaction_id>/', views.PaymentStatusView.as_view(), name='payment-status'),

    # Manual validation endpoints
    path('validate/', views.ManualValidationView.as_view(), name='manual-validation'),

    # Transaction management
    path('transactions/', views.TransactionListView.as_view(), name='transaction-list'),
    path('bulk-status/', views.BulkStatusCheckView.as_view(), name='bulk-status-check'),

    # Utility endpoints
    path('test-connection/', views.ConnectionTestView.as_view(), name='test-connection'),
    path('health/', views.health_check, name='health-check'),
]
