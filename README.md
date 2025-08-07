# Lumenario Solutions – Payment Gateway API

![Lumenario Logo](https://lmn.co.ke/black.png)

A secure, scalable, and modular Django-based API designed to handle multiple payment gateways starting with **MPesa**, and easily extendable to others like Stripe and PayPal.

---

## 🌍 Project Structure Overview

This project is structured with **reusability**, **versioning**, and **API-client separation** in mind. Below is a breakdown of the major Django apps and their internal folder organization.

```
lmn_payment_gateways/
├── mpesa/
├── core/
├── clients/
├── lmn_payment_gateways/     # Root Django project config
├── manage.py
```

---

## 🧩 Django Apps Breakdown

### 1. `mpesa/` — MPesa Payment Gateway Integration

Handles all logic related to Safaricom MPesa:

```
mpesa/
├── models/                   # MPesa-specific models (e.g., transactions)
├── views/                    # Class-based or function-based views
├── services/                 # Business logic: API calls, STK handling
├── serializers/              # DRF serializers for validating request/response data
├── api/v1/                   # Versioned URL routing and views
├── urls.py                   # Includes versioned URLs
├── tests/                    # Unit & integration tests
```

**Example Flow:**

- `/api/mpesa/v1/stk-push/` → Calls view → Uses service → Stores data via model → Returns response via serializer.

---

### 2. `core/` — Shared Utilities Across Apps

Contains reusable logic or helpers used by all payment gateways:

```
core/
├── utils/                    # Common utilities (e.g., phone number formatting)
├── services/                 # Shared services like logging
├── decorators/               # Custom decorators (e.g., API key auth)
├── middleware/               # Optional custom middleware
```

**Example Use Case:**

- `core.utils.phone.normalize_number()` used in MPesa or Stripe services.

---

### 3. `clients/` — API Clients and Access Management

This app manages **third-party apps or businesses** that consume your API:

```
clients/
├── models/                   # Stores clients, API keys, usage logs
├── views/                    # Endpoints to register/manage clients
├── serializers/              # Serialize client data
├── permissions/              # Optional custom DRF permission classes
├── urls.py
├── admin.py
```

**Example Use Case:**

- A client (e.g., school or shop) is issued an API key and can access `/api/mpesa/v1/stk-push/` using that key.

---

## 🚦 API Versioning

Versioning is handled in the app using the `/api/v1/` structure:

```
mpesa/
└── api/
    └── v1/
        ├── urls.py
        ├── views.py
        └── serializers.py
```

This allows for:

- **Backward compatibility** with older clients.
- Future updates via `/api/v2/`, `/api/v3/`, etc.

---

## 🛠 Project Flow Summary

1. **Client makes a request** to an endpoint (e.g., `/api/mpesa/v1/stk-push/`).
2. Request hits the **versioned view** under `mpesa/api/v1/views.py`.
3. View uses a **serializer** to validate input.
4. Business logic is handled inside `mpesa/services/`.
5. Data is stored or fetched via models in `mpesa/models/`.
6. **Utilities from `core/`** (e.g., phone formatting) may be used.
7. The response is serialized and returned to the client.
8. Authentication can be enforced using **decorators or permissions**.

---

## ✅ Setup Instructions

1. **Clone the project**

   ```bash
   git clone https://github.com/your-username/lmn_payment_gateways.git
   cd lmn_payment_gateways
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install requirements**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations**

   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Create a superuser**

   ```bash
   python manage.py createsuperuser
   ```

6. **Run server**
   ```bash
   python manage.py runserver
   ```

---

## 🔒 Security Notes

- All gateway credentials are encrypted at rest.
- API requests are secured using custom API keys.
- Django REST Framework permission classes control access per client.

---

## 📡 Upcoming Gateways

- ✅ MPesa
- ⏳ Stripe (Next)
- ⏳ PayPal
- ⏳ Flutterwave

---

## 👨‍💻 Developed by

**Lumenario Solutions**  
Building digital infrastructure for modern Africa.  
🌐 [lmn.co.ke](https://lmn.co.ke)

---

## 📄 License

MIT License – See `LICENSE` file for details.
