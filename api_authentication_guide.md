# API Key Authentication System Guide

## Overview

The Lumenario Payment Gateway uses an exclusive API key authentication system that completely replaces Django's session-based authentication for all API endpoints. This system is designed for public API access and provides secure, scalable authentication for payment gateway operations.

## Authentication Methods

### 1. API Key Authentication (Primary)

The primary authentication method uses API key and secret pairs to authenticate clients.

#### Headers Format

**Option A: Authorization Header**

```http
Authorization: ApiKey <api_key>:<api_secret>
```

**Option B: Separate Headers**

```http
X-API-Key: <api_key>
X-API-Secret: <api_secret>
```

#### Example Request

```bash
curl -X POST https://api.lmn.co.ke/api/v1/mpesa/initiate/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key_here" \
  -H "X-API-Secret: your_api_secret_here" \
  -d '{
    "phone_number": "+254712345678",
    "amount": "100.00",
    "description": "Test payment"
  }'
```

### 2. HMAC Signature Authentication (Enhanced Security)

For enhanced security, clients can use HMAC signature authentication.

#### Required Headers

```http
X-API-Key: <api_key>
X-Signature: <hmac_sha256_signature>
X-Timestamp: <unix_timestamp>
```

#### Signature Calculation

```python
import hmac
import hashlib
import time

# Create string to sign
method = "POST"
uri = "/api/v1/mpesa/initiate/"
timestamp = str(int(time.time()))
body = '{"phone_number":"+254712345678","amount":"100.00"}'

string_to_sign = f"{method}{uri}{timestamp}{body}"

# Calculate signature
signature = hmac.new(
    api_secret.encode(),
    string_to_sign.encode(),
    hashlib.sha256
).hexdigest()
```

### 3. Multi-Authentication

The system supports multiple authentication methods simultaneously, trying API key authentication first, then signature authentication.

## Client Registration

### Automatic Registration

Clients can register themselves through the public registration endpoint:

```http
POST /api/v1/clients/register/
Content-Type: application/json

{
  "name": "Your Company Name",
  "email": "admin@yourcompany.com",
  "description": "Payment integration for our e-commerce platform",
  "plan": "free",
  "webhook_url": "https://yourwebsite.com/webhook"
}
```

### Response

```json
{
  "success": true,
  "data": {
    "client": {
      "client_id": "uuid-here",
      "name": "Your Company Name",
      "email": "admin@yourcompany.com",
      "api_key": "your_generated_api_key",
      "status": "active",
      "plan": "free",
      "created_at": "2024-01-01T00:00:00Z"
    },
    "api_secret": "your_generated_api_secret",
    "message": "Client registered successfully. Store the API secret securely - it will not be shown again."
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Important**: Store the `api_secret` securely immediately after registration. It will not be shown again.

## Client Management

### Get Client Profile

```http
GET /api/v1/clients/profile/
X-API-Key: your_api_key
X-API-Secret: your_api_secret
```

### Update Client Profile

```http
PUT /api/v1/clients/profile/
X-API-Key: your_api_key
X-API-Secret: your_api_secret
Content-Type: application/json

{
  "description": "Updated description",
  "webhook_url": "https://newwebhook.com/endpoint"
}
```

### Generate Additional API Keys

You can generate multiple API keys for different environments:

```http
POST /api/v1/clients/api-keys/
X-API-Key: your_api_key
X-API-Secret: your_api_secret
Content-Type: application/json

{
  "name": "Production Environment",
  "environment": "production",
  "permissions": ["transactions", "payments"],
  "expires_at": "2025-01-01T00:00:00Z"
}
```

## Security Features

### IP Whitelisting

Restrict API access to specific IP addresses:

```http
PUT /api/v1/clients/ip-whitelist/
X-API-Key: your_api_key
X-API-Secret: your_api_secret
Content-Type: application/json

{
  "ip_addresses": ["192.168.1.1", "10.0.0.1", "203.0.113.1"]
}
```

### Rate Limiting

All clients have configurable rate limits:

- Per minute: Default 60 requests
- Per hour: Default 1,000 requests
- Per day: Default 10,000 requests

Rate limits can be adjusted based on your subscription plan.

### Client Status Management

Clients can have the following statuses:

- `active`: Normal operation
- `suspended`: Temporarily disabled
- `disabled`: Permanently disabled

## Error Handling

### Authentication Errors

```json
{
  "error": "Authentication error",
  "message": "Invalid API credentials",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### Rate Limiting Errors

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Please try again later.",
  "code": "RATE_LIMIT_EXCEEDED"
}
```

### IP Restriction Errors

```json
{
  "error": "Authentication error",
  "message": "IP address not allowed",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## API Endpoints

### Payment Operations

- `POST /api/v1/mpesa/initiate/` - Initiate STK Push payment
- `GET /api/v1/mpesa/status/<transaction_id>/` - Check payment status
- `POST /api/v1/mpesa/validate/` - Manually validate offline payment
- `GET /api/v1/mpesa/transactions/` - List transactions
- `POST /api/v1/mpesa/bulk-status/` - Check multiple transaction statuses

### Client Management

- `POST /api/v1/clients/register/` - Register new client (public)
- `GET /api/v1/clients/profile/` - Get client profile
- `PUT /api/v1/clients/profile/` - Update client profile
- `GET /api/v1/clients/api-keys/` - List API keys
- `POST /api/v1/clients/api-keys/` - Generate new API key
- `GET /api/v1/clients/configuration/` - Get client configuration
- `PUT /api/v1/clients/configuration/` - Update client configuration
- `GET /api/v1/clients/stats/` - Get client statistics

### Utility Endpoints

- `GET /api/v1/health/` - System health check (public)
- `POST /api/v1/mpesa/test-connection/` - Test MPesa connection

## Code Examples

### Python (requests)

```python
import requests

class PaymentGatewayClient:
    def __init__(self, api_key, api_secret, base_url):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-Key': api_key,
            'X-API-Secret': api_secret,
            'Content-Type': 'application/json'
        })

    def initiate_payment(self, phone_number, amount, description):
        url = f"{self.base_url}/api/v1/mpesa/initiate/"
        data = {
            "phone_number": phone_number,
            "amount": str(amount),
            "description": description
        }
        response = self.session.post(url, json=data)
        return response.json()

    def check_status(self, transaction_id):
        url = f"{self.base_url}/api/v1/mpesa/status/{transaction_id}/"
        response = self.session.get(url)
        return response.json()

# Usage
client = PaymentGatewayClient(
    api_key="your_api_key",
    api_secret="your_api_secret",
    base_url="https://api.lmn.co.ke"
)

result = client.initiate_payment("+254712345678", 100.00, "Test payment")
print(result)
```

### PHP

```php
<?php
class PaymentGatewayClient {
    private $apiKey;
    private $apiSecret;
    private $baseUrl;

    public function __construct($apiKey, $apiSecret, $baseUrl) {
        $this->apiKey = $apiKey;
        $this->apiSecret = $apiSecret;
        $this->baseUrl = $baseUrl;
    }

    private function makeRequest($method, $endpoint, $data = null) {
        $url = $this->baseUrl . $endpoint;

        $headers = [
            'X-API-Key: ' . $this->apiKey,
            'X-API-Secret: ' . $this->apiSecret,
            'Content-Type: application/json'
        ];

        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);

        if ($data) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
        }

        $response = curl_exec($ch);
        curl_close($ch);

        return json_decode($response, true);
    }

    public function initiatePayment($phoneNumber, $amount, $description) {
        $data = [
            'phone_number' => $phoneNumber,
            'amount' => (string)$amount,
            'description' => $description
        ];

        return $this->makeRequest('POST', '/api/v1/mpesa/initiate/', $data);
    }

    public function checkStatus($transactionId) {
        return $this->makeRequest('GET', "/api/v1/mpesa/status/{$transactionId}/");
    }
}

// Usage
$client = new PaymentGatewayClient(
    'your_api_key',
    'your_api_secret',
    'https://api.lmn.co.ke'
);

$result = $client->initiatePayment('+254712345678', 100.00, 'Test payment');
print_r($result);
?>
```

### Node.js

```javascript
const axios = require("axios");

class PaymentGatewayClient {
  constructor(apiKey, apiSecret, baseUrl) {
    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.baseUrl = baseUrl;

    this.client = axios.create({
      baseURL: baseUrl,
      headers: {
        "X-API-Key": apiKey,
        "X-API-Secret": apiSecret,
        "Content-Type": "application/json",
      },
    });
  }

  async initiatePayment(phoneNumber, amount, description) {
    try {
      const response = await this.client.post("/api/v1/mpesa/initiate/", {
        phone_number: phoneNumber,
        amount: amount.toString(),
        description: description,
      });
      return response.data;
    } catch (error) {
      return error.response.data;
    }
  }

  async checkStatus(transactionId) {
    try {
      const response = await this.client.get(
        `/api/v1/mpesa/status/${transactionId}/`
      );
      return response.data;
    } catch (error) {
      return error.response.data;
    }
  }
}

// Usage
const client = new PaymentGatewayClient(
  "your_api_key",
  "your_api_secret",
  "https://api.lmn.co.ke"
);

client
  .initiatePayment("+254712345678", 100.0, "Test payment")
  .then((result) => console.log(result))
  .catch((error) => console.error(error));
```

## Testing and Development

### Sandbox Environment

Use the sandbox environment for testing:

- API Base URL: `https://sandbox-api.lmn.co.ke`
- MPesa environment: `sandbox`
- Test phone numbers: Use MPesa sandbox test numbers

### Health Check

Monitor API availability:

```http
GET /api/v1/health/
```

Response:

```json
{
  "status": "ok",
  "message": "Service health check",
  "services": {
    "database": "ok",
    "cache": "ok",
    "api": "ok"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Migration from User-based Authentication

If you're migrating from a user-based system:

1. **Replace permissions**: Use `IsValidClient` instead of `IsAuthenticated`
2. **Update views**: Ensure `request.user` is treated as a `Client` object
3. **Type checking**: Add explicit client type validation
4. **Error handling**: Update error messages for API key authentication
5. **Tests**: Update all tests to use API key authentication

## Best Practices

1. **Security**:

   - Store API secrets securely (environment variables, key vaults)
   - Use HTTPS for all API calls
   - Implement IP whitelisting for production
   - Rotate API keys regularly

2. **Error Handling**:

   - Always check response status codes
   - Implement retry logic for transient errors
   - Log authentication failures for monitoring

3. **Performance**:

   - Cache API credentials where appropriate
   - Use connection pooling for high-volume applications
   - Monitor rate limits and implement client-side throttling

4. **Monitoring**:
   - Track API usage and performance
   - Set up alerts for authentication failures
   - Monitor rate limit violations

## Support

For technical support and questions:

- Email: support@same.new
- Documentation: https://docs.same.new
- GitHub Issues: https://github.com/Lumenario-Solutions/gateways/issues

## Changelog

### v1.0.0 (Current)

- Complete API key authentication system
- Multi-authentication support
- HMAC signature authentication
- IP whitelisting
- Rate limiting
- Comprehensive client management
- MPesa integration
- Full test coverage
