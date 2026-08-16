# E-Commerce API Platform - Complete Documentation

**Version**: 1.0.0 | **Last Updated**: January 2026

## 📋 Table of Contents
1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Complete User Journey: Signup to Checkout](#-complete-user-journey-signup-to-checkout)
5. [Flow Testing & Validation](#-flow-testing--validation-guide)
6. [System Architecture](#-system-architecture)
7. [Database Models](#-database-models)
8. [User Management](#user-management)
9. [Store & Products](#store--products)
10. [Orders & Cart](#orders--cart)
11. [Payments & Transactions](#payments--transactions)
12. [Authentication & Verification](#authentication--verification)
13. [API Endpoints](#api-endpoints)
14. [Setup & Deployment](#setup--deployment)
15. [Development Guide](#development-guide)
16. [Security Features](#security-features)
17. [Email & Notifications](#email--notifications)
18. [Background Tasks & Celery](#background-tasks--celery)
19. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

**Dandelionz** is a comprehensive multi-vendor e-commerce API platform built with Django and Django REST Framework. It enables vendors to list and manage products, customers to browse and purchase items, delivery agents to track orders, and administrators to oversee the entire marketplace ecosystem.

### Core Features:
- **Multi-Vendor Architecture**: Complete support for multiple vendors managing independent product catalogs
- **JWT Authentication**: Secure token-based authentication with 15-minute access token lifetime and 14-day refresh tokens
- **Email Verification**: Automated email verification workflow with token-based validation
- **Paystack Integration**: Full payment gateway integration with webhook support and transaction tracking
- **Order Management**: Complete order lifecycle (PENDING → PAID → SHIPPED → DELIVERED) with status tracking
- **Wallet System**: User financial wallets with credit/debit transactions and audit trails
- **Role-Based Access Control**: Admin, Business Admin, Vendor, Customer, and Delivery Agent roles
- **Product Catalog**: Full CRUD operations with 16 product categories, reviews, and ratings
- **Shopping Cart**: Add/remove items with real-time subtotal calculations
- **Favorites/Wishlist**: Product favorites management for customers
- **Referral System**: Unique referral codes with bonus tracking
- **Delivery Management**: Delivery agent assignment and tracking
- **Admin Analytics**: Business admin dashboard with vendor and order analytics
- **Docker & Containerization**: Full Docker Compose setup for development and production
- **API Documentation**: Auto-generated Swagger/OpenAPI docs with DRF YASG and DRF Spectacular

---

## 🛠️ Tech Stack

### Core Framework & Libraries
| Component | Version | Purpose |
|-----------|---------|---------|
| Django | 5.2.7 | Web framework |
| Django REST Framework | 3.16.1 | REST API development |
| Django Simple JWT | 5.5.1 | JWT authentication |
| PostgreSQL | Latest | Primary database |
| Redis | Latest | Caching & message broker |

### Background Processing & Async
| Component | Version | Purpose |
|-----------|---------|---------|
| Celery | 5.5.3 | Distributed task queue |
| Django Celery Beat | 2.8.1 | Periodic task scheduler |
| Django Celery Results | 2.6.0 | Task result persistence |

### External Services & Integrations
| Component | Version | Purpose |
|-----------|---------|---------|
| Cloudinary | 1.44.1 | Image storage & transformation |
| Paystack | - | Payment gateway integration |
| Django CORS Headers | 4.9.0 | Cross-origin request handling |

### API Documentation & Schema
| Component | Version | Purpose |
|-----------|---------|---------|
| DRF YASG | 1.21.11 | Swagger/OpenAPI UI & generation |
| DRF Spectacular | 0.28.0 | Advanced OpenAPI 3.0+ schema |

### Deployment & Infrastructure
| Component | Version | Purpose |
|-----------|---------|---------|
| Docker | Latest | Containerization |
| Docker Compose | Latest | Multi-container orchestration |
| Gunicorn | 23.0.0 | WSGI application server |
| WhiteNoise | 6.11.0 | Static file serving in production |
| psycopg2-binary | 2.9.11 | PostgreSQL database adapter |

### Utilities & Tools
| Component | Version | Purpose |
|-----------|---------|---------|
| python-dotenv | 1.1.1 | Environment variable management |
| Pillow | 12.0.0 | Image processing |
| Django Admin Trap | 1.1.1 | Admin interface security |

---

## 📁 Project Structure

```
e_commerce_api/                         # Project root
├── authentication/                     # Authentication & user verification
│   ├── auth/
│   │   ├── views.py                   # Login, register, token refresh
│   │   ├── services.py                # Auth business logic
│   │   └── __pycache__/
│   ├── verification/
│   │   ├── views.py                   # Email verification, password reset
│   │   ├── services.py                # Verification workflows
│   │   ├── emails.py                  # Email templates & sending
│   │   ├── tasks.py                   # Celery email tasks
│   │   ├── tokens.py                  # Token generation & validation
│   │   └── __pycache__/
│   ├── core/
│   │   ├── base_view.py               # BaseViewSet with common functionality
│   │   ├── email_backend.py           # Custom SMTP backend with retry logic
│   │   ├── exceptions.py              # Custom exception classes
│   │   ├── jwt_utils.py               # JWT token utilities
│   │   ├── permissions.py             # Role-based permissions (IsAdmin, IsVendor, etc)
│   │   ├── referral_service.py        # Referral code generation & tracking
│   │   ├── response.py                # Standardized response wrapper
│   │   └── __pycache__/
│   ├── models.py                      # CustomUser model with roles
│   ├── admin.py                       # Admin interface configuration
│   ├── serializers.py                 # User auth serializers
│   ├── serializers_admin.py           # Admin-specific serializers
│   ├── urls.py                        # Auth endpoints
│   ├── urls_admin.py                  # Admin auth endpoints
│   ├── views.py                       # User endpoints
│   ├── views_admin.py                 # Admin endpoints
│   └── __pycache__/
│
├── users/                              # User profiles & management
│   ├── models.py                      # Vendor, Customer, BusinessAdmin, Notification, DeliveryAgent
│   ├── services/
│   │   ├── __init__.py
│   │   ├── payout_service.py          # Vendor payout processing
│   │   ├── profile_resolver.py        # User profile type resolution
│   │   ├── services.py                # User business logic
│   │   └── __pycache__/
│   ├── admin.py                       # User admin interface
│   ├── serializers.py                 # User serializers
│   ├── urls.py                        # User profile endpoints
│   ├── views.py                       # Profile management views
│   ├── signals.py                     # Django signals (profile creation on user signup)
│   ├── tasks.py                       # Celery tasks (notifications, payouts)
│   ├── tests.py                       # User tests
│   └── __pycache__/
│
├── store/                              # Products, cart, favorites
│   ├── models.py                      # Product, Cart, CartItem, Favorite, Review
│   ├── management/
│   │   ├── __init__.py
│   │   ├── __pycache__/
│   │   └── commands/                  # Custom management commands
│   ├── admin.py                       # Product admin interface
│   ├── serializers.py                 # Product & cart serializers
│   ├── urls.py                        # Product & cart endpoints
│   ├── views.py                       # Product, cart, review views
│   ├── signals.py                     # Product signals
│   ├── tasks.py                       # Celery tasks (bulk operations)
│   ├── tests.py                       # Store tests
│   └── __pycache__/
│
├── transactions/                       # Orders, payments, wallets
│   ├── models.py                      # Order, Payment, Wallet, Refund, InstallmentPlan, etc
│   ├── paystack.py                    # Paystack API integration & webhook handling
│   ├── admin.py                       # Transaction admin interface
│   ├── serializers.py                 # Order & payment serializers
│   ├── urls.py                        # Transaction endpoints
│   ├── views.py                       # Order & payment views
│   ├── signals.py                     # Order signals
│   ├── tasks.py                       # Celery tasks (order processing, delivery)
│   ├── tests.py                       # Transaction tests
│   ├── migrations/                    # Database migrations
│   └── __pycache__/
│
├── e_commerce_api/                    # Project configuration
│   ├── settings.py                    # Django settings (DB, Redis, Email, Paystack, etc)
│   ├── urls.py                        # Main URL routing (includes all apps)
│   ├── asgi.py                        # ASGI config
│   ├── wsgi.py                        # WSGI config
│   ├── celery.py                      # Celery config (broker, beat schedule)
│   └── __pycache__/
│
├── templates/                          # Email & other templates
│   └── emails/
│       ├── base_email.html            # Base email template
│       ├── verify_email.html          # Email verification template
│       ├── password_reset.html        # Password reset template
│       ├── product_approval.html      # Product approval notification
│       └── product_rejection.html     # Product rejection notification
│
├── static/                             # Static files (development)
│   └── logo/
│
├── staticfiles/                        # Collected static files (production)
│   ├── admin/
│   ├── cloudinary/
│   ├── drf-yasg/                      # Swagger UI resources
│   ├── rest_framework/                # DRF static resources
│   └── ...
│
├── Dockerfile                          # Docker image configuration
├── docker-compose.yml                 # Multi-container orchestration
├── manage.py                           # Django CLI
├── requirements.txt                   # Python dependencies (65 packages)
└── README.md                           # This file
```

---

## 🚀 Complete User Journey: Signup to Checkout

This section outlines the **complete end-to-end flow** from user registration through checkout, validating that all components work together seamlessly.

### 📱 Customer Flow: Complete User Journey

```
┌─────────────────────────────────────────────────────────────────────┐
│                    1️⃣ USER REGISTRATION                             │
├─────────────────────────────────────────────────────────────────────┤
│ POST /api/auth/register/                                             │
│                                                                       │
│ Request:                                                             │
│ {                                                                    │
│   "email": "customer@example.com",                                  │
│   "password": "SecurePass123!",                                     │
│   "phone_number": "+2348012345678",                                 │
│   "full_name": "John Doe",                                          │
│   "role": "CUSTOMER",                                               │
│   "referral_code": "OPTIONAL_CODE"                                  │
│ }                                                                    │
│                                                                       │
│ Response (Status: 201):                                             │
│ {                                                                    │
│   "success": true,                                                  │
│   "data": {                                                         │
│     "user_id": "550e8400-e29b-41d4-a716-446655440000",             │
│     "email": "customer@example.com",                                │
│     "role": "CUSTOMER",                                             │
│     "is_verified": false,                                           │
│     "tokens": {                                                     │
│       "access_token": "eyJhbGc...",                                 │
│       "refresh_token": "eyJhbGc...",                                │
│       "access_expires_in": 900,     // 15 minutes                   │
│       "refresh_expires_in": 1209600  // 14 days                     │
│     }                                                               │
│   },                                                                │
│   "message": "Registration successful. Please verify your email."   │
│ }                                                                    │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • CustomUser created with role=CUSTOMER                           │
│   • CustomerProfile created (linked to CustomUser)                  │
│   • Wallet created for user                                         │
│   • Verification email sent (via Celery task)                       │
│   • Referral code processed (if provided)                           │
│   • JWT tokens generated                                            │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    2️⃣ EMAIL VERIFICATION                            │
├─────────────────────────────────────────────────────────────────────┤
│ POST /api/auth/email-verify/                                        │
│                                                                       │
│ Request:                                                             │
│ {                                                                    │
│   "token": "email-verification-token-from-email"                    │
│ }                                                                    │
│                                                                       │
│ Response (Status: 200):                                             │
│ {                                                                    │
│   "success": true,                                                  │
│   "message": "Email verified successfully"                          │
│ }                                                                    │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Verification token validated                                    │
│   • CustomUser.is_verified = True                                   │
│   • Email marked as verified in system                              │
│   • Welcome email sent to user                                      │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    3️⃣ USER LOGIN (if needed)                        │
├─────────────────────────────────────────────────────────────────────┤
│ POST /api/auth/login/                                               │
│                                                                       │
│ Request:                                                             │
│ {                                                                    │
│   "email": "customer@example.com",                                  │
│   "password": "SecurePass123!"                                      │
│ }                                                                    │
│                                                                       │
│ Response (Status: 200):                                             │
│ {                                                                    │
│   "success": true,                                                  │
│   "data": {                                                         │
│     "user_id": "550e8400-e29b-41d4-a716-446655440000",             │
│     "email": "customer@example.com",                                │
│     "role": "CUSTOMER",                                             │
│     "is_verified": true,                                            │
│     "tokens": {                                                     │
│       "access_token": "eyJhbGc...",                                 │
│       "refresh_token": "eyJhbGc..."                                 │
│     }                                                               │
│   }                                                                 │
│ }                                                                    │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Email & password validated                                      │
│   • JWT tokens issued                                               │
│   • Login activity logged                                           │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                4️⃣ UPDATE PROFILE WITH SHIPPING ADDRESS             │
├─────────────────────────────────────────────────────────────────────┤
│ PATCH /api/user/profile/                                            │
│ (Requires: Authorization Bearer {access_token})                     │
│                                                                       │
│ Request:                                                             │
│ {                                                                    │
│   "full_name": "John Doe",                                          │
│   "phone_number": "+2348012345678",                                 │
│   "shipping_address": "123 Main St, Lagos",                         │
│   "shipping_city": "Lagos",                                         │
│   "shipping_state": "Lagos",                                        │
│   "shipping_country": "Nigeria",                                    │
│   "shipping_postal_code": "100001",                                 │
│   "shipping_latitude": 6.5244,    // CRITICAL for delivery fee      │
│   "shipping_longitude": 3.3792    // CRITICAL for delivery fee      │
│ }                                                                    │
│                                                                       │
│ Response (Status: 200):                                             │
│ {                                                                    │
│   "success": true,                                                  │
│   "data": {                                                         │
│     "user_uuid": "550e8400-e29b-41d4-a716-446655440000",           │
│     "full_name": "John Doe",                                        │
│     "email": "customer@example.com",                                │
│     "shipping_address": "123 Main St, Lagos",                       │
│     "shipping_latitude": 6.5244,                                    │
│     "shipping_longitude": 3.3792                                    │
│   }                                                                 │
│ }                                                                    │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • CustomerProfile updated with shipping info                      │
│   • Coordinates stored for delivery calculations                    │
│   • Profile saved to database                                       │
│                                                                       │
│ ⚠️  IMPORTANT: Shipping latitude/longitude are REQUIRED for         │
│     checkout to succeed. Delivery fees are calculated from          │
│     customer location to vendor location.                           │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│              5️⃣ BROWSE PRODUCTS & ADD TO FAVORITES                 │
├─────────────────────────────────────────────────────────────────────┤
│ A) GET PRODUCTS                                                      │
│                                                                       │
│    GET /api/store/products/                                         │
│    ?min_price=10000&max_price=500000                                │
│    &category=electronics                                            │
│    &search=phone                                                    │
│    &ordering=-price                                                 │
│                                                                       │
│    Response includes:                                               │
│    • Product list with approved products only                       │
│    • Filtering & search applied                                     │
│    • Pricing with discounts applied                                 │
│                                                                       │
│ B) GET PRODUCT DETAILS                                              │
│                                                                       │
│    GET /api/store/products/{slug}/                                  │
│                                                                       │
│    Response includes:                                               │
│    • Full product info                                              │
│    • All images (main image first)                                  │
│    • Available variants                                             │
│    • Customer reviews & ratings                                     │
│    • Stock status                                                   │
│                                                                       │
│ C) ADD TO FAVORITES (Optional)                                      │
│                                                                       │
│    POST /api/store/favourites/add/                                  │
│    {                                                                 │
│      "slug": "iphone-15-pro"                                        │
│    }                                                                 │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Only approved products displayed                                │
│   • Search/filtering applied                                        │
│   • Product images fetched from Cloudinary                          │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    6️⃣ ADD ITEMS TO CART                             │
├─────────────────────────────────────────────────────────────────────┤
│ POST /api/store/cart/add/                                           │
│                                                                       │
│ Request:                                                             │
│ {                                                                    │
│   "slug": "iphone-15-pro",                                          │
│   "quantity": 2                                                     │
│ }                                                                    │
│                                                                       │
│ Response (Status: 201):                                             │
│ {                                                                    │
│   "success": true,                                                  │
│   "data": {                                                         │
│     "id": 1,                                                        │
│     "product": "iphone-15-pro",                                     │
│     "quantity": 2,                                                  │
│     "price_per_item": "1200000.00",                                 │
│     "discount_percentage": 10,                                      │
│     "final_price": "1080000.00",   // After discount                │
│     "subtotal": "2160000.00"       // quantity * final_price        │
│   },                                                                │
│   "message": "Item added to cart"                                   │
│ }                                                                    │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Get or create Cart for user                                     │
│   • Get or create CartItem (product in cart)                        │
│   • If item already in cart, increment quantity                     │
│   • Store product slug for later reference                          │
│                                                                       │
│ NOTES:                                                              │
│   • Each user has ONE active cart                                   │
│   • Cannot have duplicate products in cart                          │
│   • Quantity increments on duplicate add                            │
│   • Discounts applied at purchase time (not stored in cart)         │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    7️⃣ VIEW & MANAGE CART                            │
├─────────────────────────────────────────────────────────────────────┤
│ A) GET CART                                                          │
│                                                                       │
│    GET /api/store/cart/                                             │
│                                                                       │
│    Response:                                                         │
│    {                                                                 │
│      "id": 1,                                                       │
│      "customer_uuid": "550e8400-e29b-41d4-a716-446655440000",      │
│      "items": [                                                     │
│        {                                                             │
│          "id": 1,                                                   │
│          "product_slug": "iphone-15-pro",                           │
│          "product_name": "iPhone 15 Pro",                           │
│          "quantity": 2,                                             │
│          "price": "1200000.00",                                     │
│          "discount": 10,                                            │
│          "subtotal": "2160000.00"                                   │
│        },                                                            │
│        {                                                             │
│          "id": 2,                                                   │
│          "product_slug": "airpods-pro",                             │
│          "product_name": "AirPods Pro",                             │
│          "quantity": 1,                                             │
│          "price": "60000.00",                                       │
│          "discount": 5,                                             │
│          "subtotal": "57000.00"                                     │
│        }                                                             │
│      ],                                                              │
│      "total": "2217000.00"                                          │
│    }                                                                 │
│                                                                       │
│ B) UPDATE CART ITEM QUANTITY                                        │
│                                                                       │
│    PATCH /api/store/cart/update/                                   │
│    {                                                                 │
│      "slug": "iphone-15-pro",                                       │
│      "quantity": 3                                                  │
│    }                                                                 │
│                                                                       │
│    Setting quantity to 0 removes item.                              │
│                                                                       │
│ C) REMOVE FROM CART                                                 │
│                                                                       │
│    DELETE /api/store/cart/remove/{slug}/                            │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Cart with all items retrieved                                   │
│   • Subtotals calculated (with discounts)                           │
│   • Cart total calculated                                           │
│   • OneToOne relationship ensures 1 cart per user                   │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    8️⃣ CHECKOUT & PAYMENT                            │
├─────────────────────────────────────────────────────────────────────┤
│ A) INITIATE CHECKOUT                                                 │
│                                                                       │
│    POST /api/transactions/checkout/                                 │
│    (Requires: Authorization Bearer {access_token})                  │
│                                                                       │
│    Request: {} (No body needed - uses cart items)                   │
│                                                                       │
│    Backend Validations:                                             │
│    1. ✓ User has a cart                                             │
│    2. ✓ Cart has items                                              │
│    3. ✓ Customer profile exists                                     │
│    4. ✓ Shipping address with coordinates exists                    │
│    5. ✓ Products have stock                                         │
│                                                                       │
│    Processing Steps:                                                │
│    1. Create Order (status=PENDING, payment_status=UNPAID)          │
│    2. Convert CartItems → OrderItems (with prices at purchase)      │
│    3. Retrieve vendor coordinates from Store                        │
│    4. Get customer coordinates from CustomerProfile                 │
│    5. Calculate delivery fee (distance between vendor & customer)   │
│    6. Calculate order total:                                        │
│       = Cart subtotal + Delivery fee - Discounts                    │
│    7. Create Payment record (status=PENDING)                        │
│    8. Initialize Paystack payment                                   │
│    9. Create notification for vendors                               │
│    10. Save order to database (transaction atomic)                  │
│                                                                       │
│    Response (Status: 201):                                          │
│    {                                                                 │
│      "success": true,                                               │
│      "data": {                                                       │
│        "order_id": "550e8400-e29b-41d4-a716-446655440001",         │
│        "authorization_url": "https://checkout.paystack.com/...",   │
│        "reference": "order-ref-1234567890",                         │
│        "amount": 2217000,          // Total with delivery fee        │
│        "cart_subtotal": 2217000,                                    │
│        "delivery_fee": 5000,                                        │
│        "discount": 0,                                               │
│        "order_items": [                                             │
│          {                                                           │
│            "product": "iphone-15-pro",                              │
│            "quantity": 2,                                           │
│            "price_at_purchase": "1200000.00",                       │
│            "item_subtotal": "2160000.00"                            │
│          }                                                           │
│        ],                                                            │
│        "delivery_distance": "15.3 km",                              │
│        "delivery_duration": "45 minutes"                            │
│      },                                                              │
│      "message": "Order created. Redirect to payment URL."           │
│    }                                                                 │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Atomic transaction ensures consistency                          │
│   • Order created with unique UUID                                  │
│   • OrderItem prices locked (historical record)                     │
│   • Delivery fee calculated from coordinates                        │
│   • Paystack integration initialized                                │
│   • Vendors notified of pending orders                              │
│   • Cart preserved until order confirmed                            │
│                                                                       │
│ CRITICAL COORDINATES:                                               │
│   order.restaurant_lat, order.restaurant_lng    ← Vendor location   │
│   order.customer_lat, order.customer_lng        ← Customer location │
│   Used to calculate delivery_distance & delivery_fee                │
│                                                                       │
│ B) REDIRECT TO PAYMENT                                              │
│                                                                       │
│    Client redirects to: {authorization_url}                        │
│                                                                       │
│    User fills Paystack payment form with:                           │
│    • Card number                                                    │
│    • Expiry date                                                    │
│    • CVV                                                            │
│    • OTP (if required)                                              │
│                                                                       │
│ C) PAYMENT COMPLETION                                               │
│                                                                       │
│    After payment, Paystack redirects to callback URL                │
│    (configured in settings.PAYSTACK_CALLBACK_URL)                   │
│                                                                       │
│    Client-side verifies payment with:                               │
│    POST /api/transactions/verify-payment/                           │
│    {                                                                 │
│      "reference": "order-ref-1234567890"                            │
│    }                                                                 │
│                                                                       │
│    Response:                                                         │
│    {                                                                 │
│      "success": true,                                               │
│      "data": {                                                       │
│        "order_id": "550e8400-e29b-41d4-a716-446655440001",         │
│        "status": "PAID",                                            │
│        "payment_status": "PAID",                                    │
│        "amount": 2217000,                                           │
│        "reference": "order-ref-1234567890",                         │
│        "verified_at": "2024-01-08T11:00:00Z"                        │
│      }                                                               │
│    }                                                                 │
│                                                                       │
│ D) WEBHOOK VERIFICATION (Backend - Async)                           │
│                                                                       │
│    Paystack sends webhook when payment completes:                   │
│    POST /api/transactions/webhook/                                  │
│                                                                       │
│    Webhook payload (from Paystack):                                 │
│    {                                                                 │
│      "event": "charge.success",                                     │
│      "data": {                                                       │
│        "reference": "order-ref-1234567890",                         │
│        "amount": 2217000,                                           │
│        "status": "success",                                         │
│        "customer": {                                                 │
│          "email": "customer@example.com"                            │
│        }                                                             │
│      }                                                               │
│    }                                                                 │
│                                                                       │
│    Backend processes webhook:                                       │
│    1. Verify HMAC-SHA512 signature (prevents spoofing)              │
│    2. Find payment by reference                                     │
│    3. Verify payment status is success                              │
│    4. Update Payment.verified = True                                │
│    5. Update Order.payment_status = 'PAID'                          │
│    6. For each item vendor in order:                                │
│       • Credit vendor wallet:                                       │
│         vendor_share = item_subtotal * (1 - 10% commission)        │
│       • Create WalletTransaction record                             │
│       • Create TransactionLog for audit                             │
│    7. Create order confirmation notification                        │
│    8. Send order confirmation email                                 │
│    9. Async task: Notify all vendors ("Order paid, ready now")     │
│   10. Async task: Notify all admins ("New paid order for review")  │
│                                                                       │
│    Vendor Crediting Calculation:                                    │
│    ┌─────────────────────────────────────────┐                      │
│    │ Item subtotal: ₦2,160,000               │                      │
│    │ Platform commission (10%): ₦216,000     │                      │
│    │ Vendor receives: ₦1,944,000             │ Each vendor line item │
│    └─────────────────────────────────────────┘                      │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • HMAC signature validated                                        │
│   • Payment marked verified                                         │
│   • Order status updated to PAID                                    │
│   • Vendors credited in real-time                                   │
│   • Wallet transactions recorded                                    │
│   • Full audit trail created                                        │
│   • Email confirmations sent                                        │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│              9️⃣ ORDER CONFIRMATION & SHIPPING                       │
├─────────────────────────────────────────────────────────────────────┤
│ A) VIEW ORDER DETAILS                                                │
│                                                                       │
│    GET /api/transactions/orders/{order_id}/                         │
│                                                                       │
│    Response includes:                                               │
│    • Order ID (UUID)                                                │
│    • Status: PAID                                                   │
│    • All order items with historical prices                         │
│    • Delivery address                                               │
│    • Delivery fee & calculations                                    │
│    • Total price breakdown                                          │
│    • Tracking number (when available)                               │
│                                                                       │
│ B) ADMIN OR VENDOR MARKS ORDER AS SHIPPED                           │
│                                                                       │
│    POST /api/user/orders/{order_id}/mark_shipped/                   │
│    {                                                                 │
│      "tracking_number": "NG123456789"                               │
│    }                                                                 │
│                                                                       │
│    Access: Admin (is_staff=True) or Vendor (has store)              │
│    Status flow: PAID → SHIPPED → DELIVERED                          │
│    Response: Order updated, customer notified, marked_by shown
│                                                                       │
│ C) ADMIN OR DELIVERY AGENT MARKS ORDER AS DELIVERED                 │
│                                                                       │
│    POST /api/user/orders/{order_id}/mark_delivered/                 │
│    {}                                                                │
│                                                                       │
│    Access: Admin (is_staff=True) or Delivery Agent (assigned)       │
│                                                                       │
│    This triggers:                                                   │
│    • Order marked DELIVERED                                         │
│    • Vendors credited atomically (10% commission deducted)          │
│    • Customer receives delivery confirmation                        │
│    • All other admins notified of fulfillment completion            │
│    • Delivery agent notified (if marked by admin)                   │
│    • Can now leave product review                                   │
│                                                                       │
│ D) ORDER RECEIPT                                                    │
│                                                                       │
│    GET /api/transactions/orders/{order_id}/receipt/                 │
│                                                                       │
│    Returns printable/downloadable receipt with:                     │
│    • Invoice number                                                 │
│    • Order items with prices                                        │
│    • Total breakdown                                                │
│    • Payment status                                                 │
│    • Delivery address                                               │
│    • Customer information                                           │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Order status transitions managed                                │
│   • Timestamps recorded for each status                             │
│   • Vendor commissions calculated                                   │
│   • Delivery assignments handled                                    │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    🔟 LEAVE REVIEW & FEEDBACK                       │
├─────────────────────────────────────────────────────────────────────┤
│ POST /api/store/products/{slug}/review/add/                         │
│                                                                       │
│ Request:                                                             │
│ {                                                                    │
│   "rating": 5,                                                      │
│   "comment": "Excellent product, fast delivery!"                    │
│ }                                                                    │
│                                                                       │
│ Response:                                                            │
│ {                                                                    │
│   "success": true,                                                  │
│   "data": {                                                         │
│     "id": 1,                                                        │
│     "product": "iphone-15-pro",                                     │
│     "customer": "customer@example.com",                             │
│     "rating": 5,                                                    │
│     "comment": "Excellent product, fast delivery!",                │
│     "created_at": "2024-01-08T12:00:00Z"                            │
│   }                                                                 │
│ }                                                                    │
│                                                                       │
│ 🔗 Backend Actions:                                                 │
│   • Review created or updated (one per customer per product)        │
│   • Rating stored for product analytics                             │
│   • Review appears in product details for other customers           │
└─────────────────────────────────────────────────────────────────────┘
```

### 📊 Flow Verification Checklist

✅ **Registration & Verification**
- [ ] User registers with email/password
- [ ] JWT tokens received (access + refresh)
- [ ] Email verification token sent
- [ ] Email verified successfully
- [ ] User can login with credentials

✅ **Profile Setup**
- [ ] User profile created with CUSTOMER role
- [ ] Shipping address added to profile
- [ ] Shipping latitude/longitude stored (for delivery fee calculation)
- [ ] Profile update reflected in system

✅ **Shopping**
- [ ] Products visible in product list (approved only)
- [ ] Product details retrievable by slug
- [ ] Product filtering & search works
- [ ] Can add items to cart
- [ ] Cart persists across requests
- [ ] Can update cart quantities
- [ ] Can remove items from cart

✅ **Checkout**
- [ ] Cart has items
- [ ] User has shipping address with coordinates
- [ ] Checkout creates order with PENDING status
- [ ] CartItems converted to OrderItems
- [ ] Delivery fee calculated from coordinates
- [ ] Order total correctly calculated
- [ ] Payment record created

✅ **Payment**
- [ ] Paystack payment initialized successfully
- [ ] authorization_url returned
- [ ] Reference generated correctly
- [ ] Payment verification endpoint works
- [ ] Webhook signature validation works

✅ **Post-Payment**
- [ ] Vendors credited to wallets
- [ ] Order status changes to PAID
- [ ] Payment status changes to PAID
- [ ] Wallet transactions recorded
- [ ] Notifications sent to vendors
- [ ] Customer receives confirmation email

✅ **Order Management**
- [ ] Order visible in customer orders list
- [ ] Order receipt available
- [ ] Order tracking works
- [ ] Status transitions work
- [ ] Delivery fee properly displayed

✅ **Reviews**
- [ ] Customer can leave review after delivery
- [ ] Review appears in product details
- [ ] Reviews visible to other customers

---

## 🧪 Flow Testing & Validation Guide

### Testing the Complete Customer Journey

This section provides step-by-step instructions to manually test the entire flow from signup through checkout.

#### **Prerequisites**
- API running on `http://localhost:8000`
- Swagger docs available at `http://localhost:8000/swagger/`
- Test email configured
- Paystack sandbox credentials configured

#### **Step 1: User Registration Test**

**Endpoint:** `POST /api/auth/register/`

**Test Data:**
```json
{
  "email": "testcustomer@example.com",
  "password": "TestPassword123!",
  "phone_number": "+2348012345678",
  "full_name": "Test Customer",
  "role": "CUSTOMER"
}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "tokens": {
      "access_token": "eyJhbGc...",
      "refresh_token": "eyJhbGc..."
    }
  }
}
```

**Validation Points:**
- ✅ Status code 201
- ✅ User UUID generated
- ✅ JWT tokens issued
- ✅ Email verification link sent
- ✅ CustomerProfile created
- ✅ Wallet created

---

#### **Step 2: Email Verification Test**

**Check email** for verification link and extract token.

**Endpoint:** `POST /api/auth/email-verify/`

**Test Data:**
```json
{
  "token": "{email_token_from_email}"
}
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Email verified successfully"
}
```

**Validation Points:**
- ✅ Status code 200
- ✅ CustomUser.is_verified = true
- ✅ Verification email marked in system

---

#### **Step 3: Login Test**

**Endpoint:** `POST /api/auth/login/`

**Test Data:**
```json
{
  "email": "testcustomer@example.com",
  "password": "TestPassword123!"
}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "tokens": {
      "access_token": "eyJhbGc...",
      "refresh_token": "eyJhbGc..."
    }
  }
}
```

**Validation Points:**
- ✅ Status code 200
- ✅ Access token valid
- ✅ Can use token in subsequent requests

**Save the access token** for next steps (use as: `Authorization: Bearer {access_token}`)

---

#### **Step 4: Update Profile with Shipping Address**

**Endpoint:** `PATCH /api/user/profile/`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Test Data:**
```json
{
  "full_name": "Test Customer",
  "phone_number": "+2348012345678",
  "shipping_address": "123 Main Street",
  "shipping_city": "Lagos",
  "shipping_state": "Lagos",
  "shipping_country": "Nigeria",
  "shipping_postal_code": "100001",
  "shipping_latitude": 6.5244,
  "shipping_longitude": 3.3792
}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "shipping_address": "123 Main Street",
    "shipping_latitude": 6.5244,
    "shipping_longitude": 3.3792
  }
}
```

**Validation Points:**
- ✅ Status code 200
- ✅ Profile updated
- ✅ Coordinates stored (critical for delivery fee calculation)
- ✅ Subsequent requests can retrieve updated profile

---

#### **Step 5: Browse Products**

**Endpoint:** `GET /api/store/products/?category=electronics&min_price=10000&max_price=1000000`

**Headers:**
```
Authorization: Bearer {access_token}
```

**Expected Response:**
```json
{
  "success": true,
  "data": [
    {
      "slug": "iphone-15-pro",
      "name": "iPhone 15 Pro",
      "price": "1200000.00",
      "discount": 10,
      "stock": 50,
      "approval_status": "approved",
      "publish_status": "submitted"
    }
  ]
}
```

**Validation Points:**
- ✅ Only approved products shown
- ✅ Filtering by category works
- ✅ Price filtering works
- ✅ All required fields present

**Note:** Save a product slug (e.g., `iphone-15-pro`) for next steps.

---

#### **Step 6: Add Items to Cart**

**Endpoint:** `POST /api/store/cart/add/`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Test Data:**
```json
{
  "slug": "iphone-15-pro",
  "quantity": 2
}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "product": "iphone-15-pro",
    "quantity": 2,
    "subtotal": "2160000.00"
  }
}
```

**Validation Points:**
- ✅ Status code 201
- ✅ CartItem created
- ✅ Quantity stored correctly
- ✅ Subtotal calculated with discount applied

**Add another item** to cart to test multi-vendor scenario:
```json
{
  "slug": "another-product",
  "quantity": 1
}
```

---

#### **Step 7: View Cart**

**Endpoint:** `GET /api/store/cart/`

**Headers:**
```
Authorization: Bearer {access_token}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "items": [
      {
        "id": 1,
        "product_slug": "iphone-15-pro",
        "quantity": 2,
        "subtotal": "2160000.00"
      },
      {
        "id": 2,
        "product_slug": "another-product",
        "quantity": 1,
        "subtotal": "540000.00"
      }
    ],
    "total": "2700000.00"
  }
}
```

**Validation Points:**
- ✅ All cart items displayed
- ✅ Subtotals calculated correctly
- ✅ Cart total is sum of all items
- ✅ Multiple vendors possible

---

#### **Step 8: Checkout (Create Order)**

**Endpoint:** `POST /api/transactions/checkout/`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request:** Empty body (uses cart items automatically)
```json
{}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "order_id": "550e8400-e29b-41d4-a716-446655440001",
    "authorization_url": "https://checkout.paystack.com/...",
    "reference": "order-ref-1234567890",
    "amount": 2700000,
    "order_items": [
      {
        "product": "iphone-15-pro",
        "quantity": 2,
        "price_at_purchase": "1200000.00"
      }
    ],
    "delivery_fee": 5000,
    "delivery_distance": "15.3 km"
  }
}
```

**Validation Points:**
- ✅ Status code 201
- ✅ Order created with PENDING status
- ✅ Order UUID generated
- ✅ CartItems converted to OrderItems
- ✅ Payment record created
- ✅ Paystack initialized
- ✅ authorization_url provided
- ✅ Delivery fee calculated from coordinates
- ✅ Order total = cart_subtotal + delivery_fee
- ✅ Order.payment_status = 'UNPAID'
- ✅ Order.status = 'PENDING'

**Save the order_id and reference** for payment verification.

---

#### **Step 9: Verify Payment**

**Endpoint:** `POST /api/transactions/verify-payment/`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Test Data:**
```json
{
  "reference": "order-ref-1234567890"
}
```

**In Paystack Sandbox:**
- Complete payment with test card: `4111 1111 1111 1111`
- OTP: `123456`
- Enter any future expiry date

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "order_id": "550e8400-e29b-41d4-a716-446655440001",
    "status": "PAID",
    "payment_status": "PAID",
    "amount": 2700000
  }
}
```

**Validation Points:**
- ✅ Status code 200
- ✅ Payment marked verified
- ✅ Order status = PAID
- ✅ Order payment_status = PAID

---

#### **Step 10: Verify Webhook Processing**

**Backend automatically processes** Paystack webhook when payment completes.

**Check:**
1. **Vendor wallets credited:**
   ```
   Endpoint: GET /api/transactions/wallet/
   Expected: Vendor balance increased by (item_subtotal * 0.9)
   ```

2. **Wallet transactions created:**
   ```
   Endpoint: GET /api/transactions/wallet/transactions/
   Expected: CREDIT transaction for each vendor
   ```

3. **Order status updated:**
   ```
   Endpoint: GET /api/transactions/orders/{order_id}/
   Expected: payment_status = 'PAID', status = 'PAID'
   ```

**Validation Points:**
- ✅ Order.payment_status changed to PAID
- ✅ Vendors credited in wallets
- ✅ WalletTransactions created
- ✅ TransactionLogs created for audit
- ✅ Platform commission (10%) deducted
- ✅ Notifications sent to vendors

---

#### **Step 11: View Order Details**

**Endpoint:** `GET /api/transactions/orders/{order_id}/`

**Headers:**
```
Authorization: Bearer {access_token}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "order_id": "550e8400-e29b-41d4-a716-446655440001",
    "status": "PAID",
    "payment_status": "PAID",
    "total_price": "2700000.00",
    "delivery_fee": "5000.00",
    "order_items": [
      {
        "product": "iphone-15-pro",
        "quantity": 2,
        "price_at_purchase": "1200000.00",
        "item_subtotal": "2400000.00"
      }
    ],
    "ordered_at": "2024-01-08T10:30:00Z"
  }
}
```

**Validation Points:**
- ✅ Order fully populated
- ✅ Historical prices preserved
- ✅ Delivery fee included
- ✅ Status transitions visible

---

#### **Step 12: Get Order Receipt**

**Endpoint:** `GET /api/transactions/orders/{order_id}/receipt/`

**Headers:**
```
Authorization: Bearer {access_token}
```

**Expected Response:**
```json
{
  "success": true,
  "data": {
    "order_id": "550e8400-e29b-41d4-a716-446655440001",
    "invoice_number": "INV-20240108-001",
    "customer": "Test Customer",
    "items": [...],
    "subtotal": "2695000.00",
    "delivery_fee": "5000.00",
    "total": "2700000.00",
    "payment_method": "Paystack",
    "status": "PAID"
  }
}
```

**Validation Points:**
- ✅ Receipt formatted correctly
- ✅ All order details included
- ✅ Ready for printing/PDF export

---

### Common Issues & Troubleshooting

| Issue | Solution |
|-------|----------|
| **Checkout fails** with "Shipping address with coordinates required" | Make sure to update profile with shipping_latitude and shipping_longitude (Step 4) |
| **Delivery fee = 0** | Verify vendor has store_latitude/store_longitude. Check delivery service is configured. |
| **Payment verification fails** | Ensure reference matches exactly. Check Paystack credentials in settings. |
| **Vendors not credited** | Check webhook was processed. Verify payment_status = 'PAID'. Check Wallet model exists. |
| **Cart persists after checkout** | Cart is intentionally not cleared until order confirmed. This is by design. |
| **Only one item in cart** | Each user has ONE cart with unique constraint per product. Quantity is incremented. |
| **Product not visible** | Verify approval_status='approved' AND publish_status='submitted'. |

---

## 🏗️ System Architecture

### High-Level Flow

```
Client Application
       ↓
API Endpoints (REST)
       ↓
┌─────────────────────────────────────┐
│    Authentication & Verification     │
│  (JWT Tokens, Email Verification)    │
└─────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────┐
│  Core Services (User Profiles, Orders, Payments)         │
│  ┌─────────────┬────────────┬────────────┬─────────────┐ │
│  │  Users      │  Products  │  Orders    │ Payments    │ │
│  │  (Vendor,   │  (Create,  │  (CRUD,    │ (Paystack,  │ │
│  │   Customer) │   Catalog) │   Status)  │  Wallet)    │ │
│  └─────────────┴────────────┴────────────┴─────────────┘ │
└──────────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────┐
│      PostgreSQL Database              │
│  (Models, Transactions, Audit Trail)  │
└──────────────────────────────────────┘
       ↓
┌──────────────────────────────────────┐
│  External Services                    │
│  ├─ Cloudinary (Image Storage)        │
│  ├─ Paystack (Payment Gateway)        │
│  ├─ Email Service (Verification)      │
│  └─ Redis (Caching/Queues)            │
└──────────────────────────────────────┘
```

### Request Processing Pipeline

1. **Request Arrival** → CORS middleware check
2. **Authentication** → JWT validation and user identification
3. **Permissions Check** → Role-based access control (Admin, Vendor, Customer)
4. **Business Logic** → View/ViewSet processing
5. **Database Operations** → Model interactions with PostgreSQL
6. **Response Serialization** → Convert to JSON response
7. **Response Return** → Send to client with standardized format

---

## 💾 Database Models

### 1. Authentication Module (`authentication/models.py`)

#### CustomUser
The core user model with role-based access control.

```python
class CustomUser(AbstractBaseUser, PermissionsMixin):
    Roles: ADMIN, BUSINESS_ADMIN, VENDOR, CUSTOMER
    
    Fields:
    - uuid (UUID, Primary Key)
    - email (unique)
    - full_name
    - phone_number
    - profile_picture (Cloudinary)
    - role (Choice field)
    - referral_code (unique, auto-generated)
    - is_verified (email verification status)
    - is_active, is_staff (admin status)
    - created_at, updated_at (timestamps)
```

**Key Methods:**
- `_generate_unique_referral_code()`: Generates unique 12-character referral codes
- `is_admin`, `is_business_admin`, `is_vendor`, `is_customer`: Role check properties

---

### 2. Users Module (`users/models.py`)

#### Vendor
Represents a store/seller on the platform.

```python
class Vendor:
    Fields:
    - user (OneToOne with CustomUser)
    - store_name
    - store_description
    - business_registration_number
    - address
    - bank_name
    - account_number
    - recipient_code (Paystack recipient)
    - is_verified_vendor (Boolean flag)
```

#### Customer
Customer profile with loyalty tracking.

```python
class Customer:
    Fields:
    - user (OneToOne with CustomUser)
    - shipping_address
    - city, country, postal_code
    - loyalty_points (integer)
```

#### BusinessAdmin
Admin user with specific permissions.

```python
class BusinessAdmin:
    Fields:
    - user (OneToOne with CustomUser)
    - position (role description)
    - can_manage_vendors (Boolean)
    - can_manage_orders (Boolean)
    - can_manage_payouts (Boolean)
    - can_manage_inventory (Boolean)
```

#### Notification
User notifications for order updates, promos, etc.

```python
class Notification:
    Fields:
    - recipient (ForeignKey to CustomUser)
    - title, message
    - is_read (Boolean)
    - created_at (timestamp)
```

#### DeliveryAgent
Delivery personnel tracking.

```python
class DeliveryAgent:
    Fields:
    - user (OneToOne with CustomUser)
    - phone
    - is_active
    - created_at
```

---

### 3. Store Module (`store/models.py`)

#### Product
Core product catalog model.

```python
class Product:
    Categories: Electronics, Fashion, Home Appliances, Beauty, Sports, 
                Automotive, Books, Toys, Groceries, Computers, Phones, 
                Jewelry, Baby Products, Pet Supplies, Office, Gaming
    
    Fields:
    - store (ForeignKey to Vendor)
    - name, slug (unique URL identifier)
    - description, category
    - price (DecimalField)
    - stock (inventory count)
    - image (Cloudinary)
    - created_at, updated_at
    
    Methods:
    - in_stock (property): Boolean check for availability
    - save(): Auto-generates unique slug
```

**Relationships:**
- One vendor → Many products
- One product → Multiple orders (through OrderItem)

#### Cart
Shopping cart for customers.

```python
class Cart:
    Fields:
    - customer (ForeignKey to CustomUser)
    - created_at, updated_at
    
    Methods:
    - total (property): Calculates sum of all CartItem subtotals
```

#### CartItem
Individual items in a cart.

```python
class CartItem:
    Fields:
    - cart (ForeignKey)
    - product (ForeignKey)
    - quantity (positive integer)
    
    Methods:
    - subtotal (property): price × quantity
```

#### Favourite
Wishlist/favorites for customers.

```python
class Favourite:
    Fields:
    - customer (ForeignKey to CustomUser)
    - product (ForeignKey)
    - added_at (timestamp)
    
    Constraints:
    - unique_together: ('customer', 'product')
```

#### Review
Product reviews and ratings.

```python
class Review:
    Fields:
    - product (ForeignKey)
    - customer (ForeignKey to CustomUser)
    - rating (1-5 or higher)
    - comment (text)
    - created_at (timestamp)
```

---

### 4. Transactions Module (`transactions/models.py`)

#### Wallet
User financial wallet for funds management.

```python
class Wallet:
    Fields:
    - user (OneToOne with CustomUser)
    - balance (DecimalField, default 0)
    - updated_at (auto timestamp)
    
    Methods:
    - credit(amount, source): Add funds (creates WalletTransaction)
    - debit(amount, source): Subtract funds (validates balance)
```

#### WalletTransaction
Transaction history for wallets.

```python
class WalletTransaction:
    Types: CREDIT, DEBIT
    
    Fields:
    - wallet (ForeignKey)
    - transaction_type (choice)
    - amount (DecimalField)
    - source (text description)
    - created_at (timestamp)
```

#### Order
Main order model coordinating purchases.

```python
class Order:
    Status: PENDING, PAID, SHIPPED, DELIVERED, CANCELED
    
    Fields:
    - order_id (UUID, unique)
    - customer (ForeignKey to CustomUser)
    - status (order status)
    - total_price (DecimalField)
    - delivery_fee (DecimalField)
    - discount (DecimalField)
    - tracking_number
    - payment_status (UNPAID, PAID)
    - ordered_at, updated_at (timestamps)
    - products (ManyToMany through OrderItem)
    
    Methods:
    - calculate_total(): Computes (subtotal - discount + delivery_fee)
    - update_total(): Updates total_price field
    - subtotal (property): Sum of all OrderItem subtotals
    - total_with_delivery (property): subtotal + delivery_fee - discount
    - is_paid (property): payment_status == 'PAID'
    - is_delivered (property): status == 'DELIVERED'
```

**Order Lifecycle:**
1. **PENDING** → Initial state after order creation
2. **PAID** → Payment verified, automatic notifications sent to vendors & admins
3. **SHIPPED** → Admin or Vendor marks as shipped (requires PAID status)
4. **DELIVERED** → Admin or Delivery Agent marks as delivered, vendors credited (requires SHIPPED status)
5. **CANCELED** → Order canceled (can happen at any stage)

**Admin Integration:**
- All admins (is_staff=True) receive notifications when order payment is verified
- Admins can mark orders as SHIPPED alongside vendors
- Admins can mark orders as DELIVERED alongside delivery agents
- All other admins are notified when an order is fulfilled

#### OrderItem
Individual items within an order.

```python
class OrderItem:
    Fields:
    - order (ForeignKey)
    - product (ForeignKey)
    - quantity (positive integer)
    - price_at_purchase (captured at order time)
    
    Methods:
    - item_subtotal (property): price_at_purchase × quantity
    - vendor (property): Gets product.store (vendor)
    - save(): Auto-captures product.price if not set
```

**Key Point:** Captures price at purchase time to preserve pricing history even if product price changes.

#### Payment
Payment processing and verification.

```python
class Payment:
    Status: PENDING, SUCCESS, FAILED
    
    Fields:
    - order (OneToOne)
    - reference (unique)
    - amount (DecimalField)
    - status (payment status)
    - gateway (default: 'Paystack')
    - paid_at (timestamp, null until successful)
    - verified (Boolean)
    - created_at (timestamp)
    
    Methods:
    - mark_as_successful(): Updates status to SUCCESS, verified=True
    
    Constraints:
    - Unique constraint on (order, reference)
    - Indexes on status and reference for quick lookup
```

#### ShippingAddress
Delivery address for orders.

```python
class ShippingAddress:
    Fields:
    - order (OneToOne)
    - full_name
    - address (text)
    - city, state, country
    - postal_code
    - phone_number
```

#### TransactionLog
Audit trail for order operations.

```python
class TransactionLog:
    Fields:
    - order (ForeignKey, nullable)
    - message (text)
    - created_at (timestamp)
    - level (INFO, WARNING, ERROR)
```

#### Refund
Refund handling for orders.

```python
class Refund:
    Status: PENDING, APPROVED, REJECTED, COMPLETED
    
    Fields:
    - order (ForeignKey)
    - reason (text)
    - amount (DecimalField)
    - status
    - created_at, updated_at
```

#### InstallmentPlan
Installment payment options.

```python
class InstallmentPlan:
    Fields:
    - order (OneToOne)
    - total_amount (DecimalField)
    - installment_count (number of payments)
    - installment_amount (per installment)
    - interest_rate
    - payment_frequency (monthly, weekly)
    - created_at
```

#### InstallmentPayment
Individual installment payments.

```python
class InstallmentPayment:
    Status: PENDING, PAID, FAILED, OVERDUE
    
    Fields:
    - plan (ForeignKey)
    - amount_due
    - status
    - due_date
    - paid_date (nullable)
```

---

## 👥 User Management

### User Roles & Permissions

#### 1. **Customer**
- Default role for regular users
- Can browse and purchase products
- Manage shopping cart and favorites
- View order history
- Access personal wallet
- Earn loyalty points
- Use referral codes

**Permissions:**
- View all public products
- Create/update own orders
- Access own order history
- Manage cart and favorites
- View/update profile

#### 2. **Vendor**
- Sell products on the platform
- Manage product catalog
- View sales analytics
- Receive payouts
- Manage store information
- Track inventory

**Permissions:**
- CRUD products (own only)
- View sales analytics
- View orders containing own products
- Request payouts
- Update store profile

#### 3. **Business Admin**
- Oversee entire platform operations
- Vendor management and approval
- Order management
- Financial oversight (payouts, commissions)
- Inventory management
- Create other admins

**Permissions:**
- Manage all vendors (approve, suspend, verify)
- View all orders
- Process payouts
- View financial reports
- Manage inventory
- Full admin access with granular permissions

#### 4. **Platform Admin**
- Super user access
- Full system control
- Staff member of Django admin

---

### Authentication Flow

```
User Registration
    ↓
[CustomUser created with role]
    ↓
Email Verification
    ↓
[is_verified = True]
    ↓
Role-Specific Profile Created
├─ CUSTOMER → Customer profile
├─ VENDOR → Vendor profile
└─ BUSINESS_ADMIN → BusinessAdmin profile
    ↓
User Ready for Login
```

### JWT Token System

**Token Endpoints:**
- `POST /api/auth/login/` - Issue access/refresh tokens
- `POST /api/auth/token/refresh/` - Refresh access token
- `POST /api/auth/token/validate/` - Validate token

**Token Structure:**
- **Access Token**: Short-lived (5-15 min), used in Authorization header
- **Refresh Token**: Long-lived (days/weeks), used to obtain new access tokens

**Header Format:**
```
Authorization: Bearer <access_token>
```

---

## 🏪 Store & Products

### Product Management

#### Creating Products (Vendor-Only)
```
POST /api/store/products/

Request:
{
    "name": "iPhone 15 Pro",
    "description": "Latest Apple smartphone",
    "category": "phones",
    "price": "1200000.00",
    "stock": 50,
    "image": <file>
}

Response:
{
    "id": 1,
    "slug": "iphone-15-pro",
    "name": "iPhone 15 Pro",
    "store": 1,  // Vendor ID
    "in_stock": true,
    "created_at": "2024-01-08T10:30:00Z"
}
```

#### Product Categories
Supported categories enable better organization:
- Electronics & Computers
- Fashion & Jewelry
- Home & Appliances
- Beauty & Personal Care
- Sports & Outdoors
- Automotive
- Books, Toys, Games
- Groceries, Pet Supplies, Office Products

#### Product Search & Filtering
```
GET /api/store/products/?category=electronics&search=phone&ordering=-price

Parameters:
- store: Filter by vendor ID
- category: Product category
- price: Price filter
- search: Search by name/description
- ordering: Sort by price or name
```

#### Unique Slug Generation
Each product gets an auto-generated slug:
- Base slug from product name
- If duplicate exists, append `-1`, `-2`, etc.
- Unique constraint ensures no collisions

---

### Shopping Cart

#### Cart Operations

**Get/Create Cart:**
```
GET /api/store/cart/

Response:
{
    "id": 1,
    "customer": "user-uuid",
    "items": [
        {
            "id": 1,
            "product": 5,
            "quantity": 2,
            "subtotal": "2400000.00"
        }
    ],
    "total": "2400000.00"
}
```

**Add Item to Cart:**
```
POST /api/store/cart/items/

Request:
{
    "product": 5,
    "quantity": 2
}
```

**Update Cart Item:**
```
PATCH /api/store/cart/items/{item_id}/

Request:
{
    "quantity": 3
}
```

**Remove Item:**
```
DELETE /api/store/cart/items/{item_id}/
```

---

### Favorites/Wishlist

**Add to Favorites:**
```
POST /api/store/favorites/

Request:
{
    "product": 5
}
```

**Get Favorites:**
```
GET /api/store/favorites/

Response:
[
    {
        "id": 1,
        "product": 5,
        "product_name": "iPhone 15 Pro",
        "added_at": "2024-01-08T10:30:00Z"
    }
]
```

---

### Product Reviews

**Create Review:**
```
POST /api/store/reviews/

Request:
{
    "product": 5,
    "rating": 5,
    "comment": "Excellent product, highly recommend!"
}
```

**Get Product Reviews:**
```
GET /api/store/products/{product_id}/reviews/

Response:
[
    {
        "id": 1,
        "customer": "user@example.com",
        "rating": 5,
        "comment": "Excellent product",
        "created_at": "2024-01-08T10:30:00Z"
    }
]
```

---

## 🛒 Orders & Cart

### Order Creation Flow

```
1. Customer adds items to cart
    ↓
2. Customer initiates checkout
    ↓
3. Order created (PENDING status)
    ↓
4. ShippingAddress linked
    ↓
5. Payment initiated
    ↓
6. Customer pays via Paystack
    ↓
7. Payment verified → payment_status = 'PAID'
    ↓
8. Vendor notified of new order
    ↓
9. Admin/Vendor marks as SHIPPED
    ↓
10. Delivery agent marks as DELIVERED
```

### Order Status Management

#### Order Statuses

| Status | Meaning | Triggered By |
|--------|---------|------------|
| **PENDING** | Order created, awaiting payment | System |
| **PAID** | Payment verified | Paystack webhook |
| **SHIPPED** | Order dispatched | Vendor/Admin |
| **DELIVERED** | Received by customer | Delivery Agent |
| **CANCELED** | Order canceled | Customer/Admin |

**Important:** 
- `status` and `payment_status` are separate fields
- An order can be PENDING with payment_status = 'PAID'
- This allows tracking payment separately from fulfillment

### Create Order

```
POST /api/transactions/orders/

Request:
{
    "items": [
        {
            "product": 5,
            "quantity": 2
        }
    ],
    "delivery_fee": "5000.00",
    "discount": "0.00",
    "shipping_address": {
        "full_name": "John Doe",
        "address": "123 Main St",
        "city": "Lagos",
        "state": "Lagos",
        "country": "Nigeria",
        "postal_code": "100001",
        "phone_number": "+2348012345678"
    }
}

Response:
{
    "order_id": "uuid-1234",
    "customer": "customer-uuid",
    "status": "PENDING",
    "total_price": "2410000.00",
    "payment_status": "UNPAID",
    "items": [...],
    "tracking_number": null,
    "created_at": "2024-01-08T10:30:00Z"
}
```

### Get Orders

**Customer's Orders:**
```
GET /api/transactions/orders/
```

**Vendor's Orders:**
```
GET /api/transactions/orders/vendor/

Returns orders containing vendor's products
```

**Admin Orders:**
```
GET /api/transactions/orders/admin/

Returns all platform orders
```

### Order Item Pricing

OrderItem captures price at purchase time:

```python
# If product price is ₦1,000,000
# OrderItem.price_at_purchase = 1,000,000

# Later, vendor updates product to ₦900,000
# OrderItem still shows ₦1,000,000 (historical price preserved)
```

**Benefit:** Prevents price disputes and maintains accurate financial records.

---

## 💳 Payments & Transactions

### Payment Processing Architecture

```
Customer Order
    ↓
[Amount Calculated]
    ↓
Paystack Integration
    ├─ Initialize Payment
    ├─ Get Payment URL
    └─ Customer Redirected
    ↓
[Customer Completes Payment]
    ↓
Paystack Webhook
    ├─ Verifies Payment
    ├─ Updates Payment model
    └─ Credits Vendors
    ↓
Order PAID Status
```

### Initialize Payment

```
POST /api/transactions/payments/initialize/

Request:
{
    "order": "order-uuid"
}

Response:
{
    "authorization_url": "https://checkout.paystack.com/...",
    "access_code": "abc123",
    "reference": "payment-ref-123"
}

Client redirects to authorization_url
```

### Verify Payment

```
POST /api/transactions/payments/verify/

Request:
{
    "reference": "payment-ref-123"
}

Response:
{
    "status": "success",
    "amount": 2410000,
    "customer_email": "customer@example.com",
    "paid_at": "2024-01-08T10:45:00Z"
}
```

### Paystack Webhook Handler

Paystack sends webhook on payment completion:

```
POST /api/transactions/payments/webhook/

Payload (from Paystack):
{
    "event": "charge.success",
    "data": {
        "reference": "payment-ref-123",
        "amount": 2410000,
        "status": "success"
    }
}

System actions:
1. Verify webhook signature (HMAC-SHA512)
2. Validate reference exists
3. Mark Payment as verified
4. Update Order.payment_status = 'PAID'
5. Credit vendors for their items
6. Create transaction logs
```

### Wallet System

#### Wallet Operations

**Get Wallet:**
```
GET /api/transactions/wallet/

Response:
{
    "balance": "50000.00",
    "user": "user-uuid",
    "updated_at": "2024-01-08T10:30:00Z"
}
```

**Credit Wallet:**
```python
# Example: Vendor receiving payment
wallet = user.wallet
wallet.credit(amount=2000000, source="Order#order-id - Commission")

# Creates:
# 1. Wallet.balance updated
# 2. WalletTransaction record created
```

**Debit Wallet:**
```python
# Example: Payout to vendor
wallet = vendor.wallet
try:
    wallet.debit(amount=2000000, source="Payout - Batch#123")
except ValueError:
    # Insufficient balance
```

#### Wallet Transaction Types

```
CREDIT Operations:
- Vendor receives payment for order
- Referral bonus added
- Admin credits for promo

DEBIT Operations:
- Payout to vendor bank account
- Refund to customer
- Withdrawal request
```

---

### Vendor Commission & Payouts

#### Commission Calculation

```
Order Total: ₦2,410,000
Platform Commission: 10%
Vendor Commission: 90%

Per Vendor Item Calculation:
Item Subtotal: ₦1,000,000
Vendor Receives: ₦1,000,000 × 90% = ₦900,000

Process:
1. Payment verified
2. Calculate vendor share per item
3. Deduct 10% platform commission
4. Credit vendor wallet with 90%
5. Create transaction log
```

#### Payout Management

**Request Payout:**
```
POST /api/user/vendor/payouts/request/

Request:
{
    "amount": "900000.00",
    "reason": "Weekly withdrawal"
}

Response:
{
    "id": 1,
    "amount": "900000.00",
    "status": "PENDING",
    "requested_at": "2024-01-08T10:30:00Z"
}
```

**Process Payout (Admin):**
```
PATCH /api/user/admin/payouts/{payout_id}/process/

Request:
{
    "action": "approve"  // or "reject"
}

System actions:
1. Validate vendor has sufficient balance
2. Debit vendor wallet
3. Initiate bank transfer via Paystack
4. Update payout status
5. Create transaction log
```

---

### Refunds

**Request Refund:**
```
POST /api/transactions/orders/{order_id}/refund/

Request:
{
    "reason": "Damaged item received"
}

Response:
{
    "id": 1,
    "order": "order-uuid",
    "amount": "2410000.00",
    "status": "PENDING",
    "created_at": "2024-01-08T10:30:00Z"
}
```

**Refund Statuses:**
- **PENDING**: Submitted, awaiting admin review
- **APPROVED**: Approved, refund processing
- **REJECTED**: Admin rejected the refund
- **COMPLETED**: Refund issued to customer

---

### Installment Payments (Future)

**Create Installment Plan:**
```
POST /api/transactions/installments/

Request:
{
    "order": "order-uuid",
    "installment_count": 3,
    "payment_frequency": "monthly"
}

Response:
{
    "plan_id": 1,
    "total_amount": "2410000.00",
    "installment_count": 3,
    "installment_amount": "803333.33",
    "due_dates": [
        "2024-02-08",
        "2024-03-08",
        "2024-04-08"
    ]
}
```

---

## 🔐 Authentication & Verification

### User Registration

```
POST /api/auth/register/

Request:
{
    "email": "user@example.com",
    "password": "secure_password123",
    "full_name": "John Doe",
    "role": "CUSTOMER"  // or VENDOR, BUSINESS_ADMIN
}

Response:
{
    "uuid": "user-uuid-1234",
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "CUSTOMER",
    "is_verified": false,
    "referral_code": "ABC123XYZ456",
    "created_at": "2024-01-08T10:30:00Z"
}
```

### Email Verification

**Send Verification Email:**
```
POST /api/auth/send-verification/

Request:
{
    "email": "user@example.com"
}

Response:
{
    "detail": "Verification email sent successfully"
}

Email contains:
- Verification token
- Link to verify endpoint
- Expiry time (usually 24 hours)
```

**Verify Email:**
```
POST /api/auth/email-verify/

Request:
{
    "email": "user@example.com",
    "token": "verification-token-from-email"
}

Response:
{
    "detail": "Email verified successfully",
    "access_token": "jwt-access-token",
    "refresh_token": "jwt-refresh-token"
}
```

**Check Verification Status:**
```
GET /api/auth/check-verification/

Response:
{
    "is_verified": true,
    "verified_at": "2024-01-08T10:45:00Z"
}
```

### Login

```
POST /api/auth/login/

Request:
{
    "email": "user@example.com",
    "password": "secure_password123"
}

Response:
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "user": {
        "uuid": "user-uuid",
        "email": "user@example.com",
        "role": "CUSTOMER",
        "is_verified": true
    }
}
```

### Token Refresh

```
POST /api/auth/token/refresh/

Request:
{
    "refresh": "refresh-token-value"
}

Response:
{
    "access": "new-access-token"
}
```

### Token Validation

```
POST /api/auth/token/validate/

Request:
{
    "token": "access-token-value"
}

Response:
{
    "valid": true,
    "user": {
        "uuid": "user-uuid",
        "email": "user@example.com",
        "role": "CUSTOMER"
    }
}
```

### Logout

```
POST /api/auth/logout/

Request:
{
    "refresh_token": "refresh-token-value"
}

Response:
{
    "detail": "Logged out successfully"
}
```

### Password Reset

**Request Password Reset:**
```
POST /api/auth/password-reset/

Request:
{
    "email": "user@example.com"
}

Response:
{
    "detail": "Password reset email sent"
}

Email contains reset token and link
```

**Confirm Password Reset:**
```
POST /api/auth/password-reset/confirm/

Request:
{
    "email": "user@example.com",
    "token": "reset-token-from-email",
    "new_password": "new_secure_password123"
}

Response:
{
    "detail": "Password reset successfully",
    "access_token": "jwt-access-token",
    "refresh_token": "jwt-refresh-token"
}
```

---

## 📡 API Endpoints

### Authentication Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/auth/register/` | Register new user | ❌ |
| POST | `/api/auth/login/` | User login | ❌ |
| POST | `/api/auth/logout/` | User logout | ✅ |
| POST | `/api/auth/token/refresh/` | Refresh access token | ❌ |
| POST | `/api/auth/token/validate/` | Validate JWT token | ✅ |
| POST | `/api/auth/send-verification/` | Send verification email | ❌ |
| POST | `/api/auth/email-verify/` | Verify email with token | ❌ |
| GET | `/api/auth/check-verification/` | Check email verification status | ✅ |
| POST | `/api/auth/password-reset/` | Request password reset | ❌ |
| POST | `/api/auth/password-reset/confirm/` | Confirm password reset | ❌ |

### User & Profile Endpoints

| Method | Endpoint | Description | Auth | Role |
|--------|----------|-------------|------|------|
| GET | `/api/user/profile/` | Get user profile | ✅ | All |
| PUT | `/api/user/profile/` | Update user profile | ✅ | All |
| PATCH | `/api/user/profile/` | Partial profile update | ✅ | All |
| POST | `/api/user/profile/change-password/` | Change password | ✅ | All |
| GET | `/api/user/notifications/` | Get user notifications | ✅ | All |
| PATCH | `/api/user/notifications/{id}/` | Mark notification as read | ✅ | All |
| GET | `/api/user/vendor/profile/` | Get vendor profile | ✅ | Vendor |
| PUT | `/api/user/vendor/profile/` | Update vendor profile | ✅ | Vendor |
| GET | `/api/user/vendor/analytics/` | Vendor sales analytics | ✅ | Vendor |
| GET | `/api/user/vendor/orders/` | Vendor's orders | ✅ | Vendor |
| GET | `/api/user/vendor/payouts/` | Vendor payout history | ✅ | Vendor |
| POST | `/api/user/vendor/payouts/request/` | Request payout | ✅ | Vendor |

### Store & Product Endpoints

| Method | Endpoint | Description | Auth | Role |
|--------|----------|-------------|------|------|
| GET | `/api/store/products/` | List all products | ❌ | All |
| GET | `/api/store/products/{id}/` | Get product details | ❌ | All |
| POST | `/api/store/products/` | Create product | ✅ | Vendor |
| PUT | `/api/store/products/{id}/` | Update product | ✅ | Vendor |
| PATCH | `/api/store/products/{id}/` | Partial product update | ✅ | Vendor |
| DELETE | `/api/store/products/{id}/` | Delete product | ✅ | Vendor |
| GET | `/api/store/cart/` | Get shopping cart | ✅ | Customer |
| POST | `/api/store/cart/items/` | Add item to cart | ✅ | Customer |
| PATCH | `/api/store/cart/items/{id}/` | Update cart item quantity | ✅ | Customer |
| DELETE | `/api/store/cart/items/{id}/` | Remove from cart | ✅ | Customer |
| GET | `/api/store/favorites/` | Get favorites list | ✅ | Customer |
| POST | `/api/store/favorites/` | Add to favorites | ✅ | Customer |
| DELETE | `/api/store/favorites/{id}/` | Remove from favorites | ✅ | Customer |
| GET | `/api/store/products/{id}/reviews/` | Get product reviews | ❌ | All |
| POST | `/api/store/reviews/` | Create review | ✅ | Customer |
| PUT | `/api/store/reviews/{id}/` | Update review | ✅ | Customer |
| DELETE | `/api/store/reviews/{id}/` | Delete review | ✅ | Customer |

### Transaction & Order Endpoints

| Method | Endpoint | Description | Auth | Role |
|--------|----------|-------------|------|------|
| GET | `/api/transactions/orders/` | List user's orders | ✅ | All |
| POST | `/api/transactions/orders/` | Create new order | ✅ | Customer |
| GET | `/api/transactions/orders/{id}/` | Get order details | ✅ | All |
| PATCH | `/api/transactions/orders/{id}/` | Update order status | ✅ | Vendor/Admin |
| DELETE | `/api/transactions/orders/{id}/` | Cancel order | ✅ | Customer |
| POST | `/api/transactions/orders/{id}/refund/` | Request refund | ✅ | Customer |
| GET | `/api/transactions/wallet/` | Get wallet balance | ✅ | All |
| POST | `/api/transactions/payments/initialize/` | Initialize payment | ✅ | Customer |
| POST | `/api/transactions/payments/verify/` | Verify payment | ✅ | Customer |
| POST | `/api/transactions/payments/webhook/` | Paystack webhook | ❌ | - |
| GET | `/api/transactions/payments/{id}/` | Get payment details | ✅ | All |

### Admin Endpoints

| Method | Endpoint | Description | Auth | Role |
|--------|----------|-------------|------|------|
| GET | `/api/user/admin/vendors/` | List all vendors | ✅ | Admin |
| PATCH | `/api/user/admin/vendors/{id}/` | Vendor actions (approve/suspend) | ✅ | Admin |
| GET | `/api/user/admin/orders/` | All platform orders | ✅ | Admin |
| PATCH | `/api/user/admin/orders/{id}/` | Manage order status | ✅ | Admin |
| GET | `/api/user/admin/analytics/` | Platform analytics | ✅ | Admin |
| GET | `/api/user/admin/payouts/` | All payout requests | ✅ | Admin |
| PATCH | `/api/user/admin/payouts/{id}/process/` | Process payout | ✅ | Admin |

---

## 🚀 Setup & Deployment

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- PostgreSQL 17
- Redis
- Git

### Local Development Setup

#### 1. Clone Repository
```bash
git clone <repository-url>
cd e_commerce_api
```

#### 2. Environment Configuration

Create `.env` file in project root:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=e_commerce_api
DB_USER=postgres
DB_PASSWORD=abrms1607
DB_HOST=db
DB_PORT=5432

# Cloudinary (Image Storage)
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# Paystack (Payment Gateway)
PAYSTACK_SECRET_KEY=sk_test_your_secret_key
PAYSTACK_PUBLIC_KEY=pk_test_your_public_key

# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@dandelionz.com

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
REDIS_URL=redis://redis:6379/1

# Referral
REFERRAL_BONUS_AMOUNT=1000.00
```

#### 3. Docker Compose Setup

```bash
# Build and start all services
docker-compose up -d

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Create sample data
docker-compose exec web python manage.py loaddata fixtures/
```

#### 4. Manual Setup (Without Docker)

```bash
# Create virtual environment
python -m venv venv

# Activate venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py makemigrations authentication store transactions users
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput

# Run development server
python manage.py runserver
```

### Database Migrations

```bash
# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations

# Rollback to specific migration
python manage.py migrate transactions 0005
```

### Accessing the Application

- **API Root**: http://localhost:8000/
- **Admin Panel**: http://localhost:8000/abtechdev/
- **Swagger UI**: http://localhost:8000/swagger/
- **ReDoc**: http://localhost:8000/redoc/

### Services

**Docker Compose Services:**

| Service | Port | Purpose |
|---------|------|---------|
| **web** | 8000 | Django API server |
| **db** | 5432 | PostgreSQL database |
| **redis** | 6379 | Cache & message broker |
| **celery-worker** | - | Async task processing |
| **celery-beat** | - | Scheduled tasks |

### Health Checks

```bash
# Check API health
curl http://localhost:8000/api/health/

# PostgreSQL connection
docker-compose exec db psql -U postgres -d e_commerce_api -c "SELECT 1"

# Redis connection
docker-compose exec redis redis-cli ping
```

---

## 🛠️ Development Guide

### Project Layout Best Practices

**App Structure:**
```
app_name/
├── models.py         # Database models
├── serializers.py    # DRF serializers
├── views.py          # API views/viewsets
├── urls.py           # URL routing
├── admin.py          # Django admin config
├── apps.py           # App configuration
├── tests.py          # Unit tests
└── [submodules]/     # Feature-specific modules
    ├── services.py   # Business logic
    ├── tasks.py      # Celery tasks
    └── signals.py    # Django signals
```

### Creating a New Feature

#### 1. Define Models
```python
# app_name/models.py
from django.db import models
from authentication.models import CustomUser

class MyModel(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### 2. Create Serializers
```python
# app_name/serializers.py
from rest_framework import serializers
from .models import MyModel

class MyModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MyModel
        fields = ['id', 'user', 'name', 'created_at']
```

#### 3. Write Views
```python
# app_name/views.py
from rest_framework import viewsets
from .models import MyModel
from .serializers import MyModelSerializer

class MyModelViewSet(viewsets.ModelViewSet):
    queryset = MyModel.objects.all()
    serializer_class = MyModelSerializer
    permission_classes = [IsAuthenticated]
```

#### 4. Register URLs
```python
# app_name/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MyModelViewSet

router = DefaultRouter()
router.register('mymodel', MyModelViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
```

### Running Tests

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test authentication

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html

# Run specific test class
python manage.py test app_name.tests.TestClassName
```

### Using Celery for Async Tasks

#### Define Task
```python
# app_name/tasks.py
from celery import shared_task
from django.core.mail import send_mail

@shared_task
def send_verification_email(user_email, token):
    send_mail(
        subject='Email Verification',
        message=f'Click here to verify: {token}',
        from_email='noreply@dandelionz.com',
        recipient_list=[user_email],
        fail_silently=False,
    )
```

#### Call Task
```python
# app_name/views.py
from .tasks import send_verification_email

# Async execution
send_verification_email.delay(user.email, verification_token)

# Scheduled execution (5 seconds from now)
send_verification_email.apply_async(
    args=[user.email, verification_token],
    countdown=5
)
```

### Database Indexing

Add indexes for frequently queried fields:

```python
class MyModel(models.Model):
    email = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]
```

---

## 🔒 Security Features

### 1. Password Security

```python
# Password hashing using Django's PBKDF2
user.set_password('plain_password')
user.save()

# Verification
if user.check_password('plain_password'):
    # Authenticated
```

### 2. JWT Token Security

- **Access tokens**: Short-lived (5-15 minutes)
- **Refresh tokens**: Long-lived (7-30 days)
- **Stored securely**: Never in localStorage (use httpOnly cookies)
- **Signature verification**: HMAC-SHA256

### 3. API Security

#### CORS Configuration
```python
CORS_ALLOWED_ORIGINS = [
    "https://dandelionz.com.ng"
]
```

#### Rate Limiting
Applied on payment and auth endpoints to prevent brute force attacks.

#### CSRF Protection
CSRF middleware enabled for form-based requests.

### 4. Data Validation

```python
# Serializer validation
class PaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('100.00')  # Minimum payment amount
    )
    
    def validate_amount(self, value):
        if value > Decimal('99999999.99'):
            raise serializers.ValidationError("Amount too large")
        return value
```

### 5. Paystack Webhook Verification

```python
import hmac
import hashlib

def verify_webhook(payload, signature):
    computed_hash = hmac.new(
        key=PAYSTACK_SECRET_KEY.encode(),
        msg=payload.encode(),
        digestmod=hashlib.sha512
    ).hexdigest()
    
    return hmac.compare_digest(computed_hash, signature)
```

### 6. SQL Injection Prevention

Django ORM automatically prevents SQL injection:

```python
# Safe: Uses parameterized queries
User.objects.filter(email=user_input)

# Never: String concatenation (DON'T DO THIS)
# User.objects.raw(f"SELECT * FROM user WHERE email = '{user_input}'")
```

### 7. Admin Interface Security

- Hidden admin URL: `/abtechdev/` instead of `/admin/`
- Django Admin Trap: Redirects known attack URLs
- Fake admin pages: Decoys at `/admin/`, `/wp-admin/`, `/administrator/`

### 8. Environment Security

- Secrets in `.env` file (git-ignored)
- DEBUG=False in production
- ALLOWED_HOSTS restricted to production domain
- SECRET_KEY unique and secure

---

## 📊 Monitoring & Logging

### Celery Task Monitoring

```bash
# View pending tasks
celery -A e_commerce_api inspect active

# Purge all pending tasks
celery -A e_commerce_api control shutdown

# Real-time task monitoring
celery -A e_commerce_api events
```

### Database Queries

```python
from django.db import connection, reset_queries
from django.test.utils import override_settings

@override_settings(DEBUG=True)
def view_function(request):
    reset_queries()
    # Your code here
    print(connection.queries)  # Prints SQL queries
```

### Transaction Logs

```python
# View all transaction logs for an order
logs = order.logs.all().order_by('-created_at')
for log in logs:
    print(f"[{log.level}] {log.created_at}: {log.message}")
```

---

## � Email & Notifications

### Email Configuration

The API uses a robust SMTP email backend with retry logic:

```python
# settings.py Configuration
EMAIL_BACKEND = 'authentication.core.email_backend.RobustSMTPEmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')  # e.g., smtp.gmail.com
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_TIMEOUT = 60  # 60-second timeout
EMAIL_CONNECTION_RETRY_ATTEMPTS = 3
EMAIL_CONNECTION_RETRY_DELAY = 2  # seconds between retries
```

### Email Templates

Located in `templates/emails/`:

| Template | Use Case |
|----------|----------|
| `base_email.html` | Base template for all emails |
| `verify_email.html` | Email verification on signup |
| `password_reset.html` | Password reset requests |
| `product_approval.html` | Vendor product approval notification |
| `product_rejection.html` | Vendor product rejection notification |

### Email Sending via Celery

```python
# authentication/verification/tasks.py
@shared_task
def send_verification_email_task(user_email, token):
    """Async task to send email verification"""
    # Automatically retried on failure
    pass
```

### Notification System

Users receive real-time notifications for:
- Order status updates
- Product approvals/rejections
- Payout confirmations
- New messages
- Promotional updates

```python
# Create notification
Notification.objects.create(
    recipient=user,
    title="Order Shipped",
    message=f"Your order #{order.order_id} has been shipped",
)

# Mark as read
notification.mark_as_read()
```

---

## ⚙️ Background Tasks & Celery

### Celery Configuration

```python
# e_commerce_api/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_commerce_api.settings')

app = Celery('e_commerce_api')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    'send-pending-notifications': {
        'task': 'users.tasks.send_pending_notifications',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    'process-refunds': {
        'task': 'transactions.tasks.process_pending_refunds',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'generate-payouts': {
        'task': 'users.tasks.generate_vendor_payouts',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM
    },
}
```

### Running Celery Workers

```bash
# Start Celery worker (in a separate terminal)
celery -A e_commerce_api worker -l info

# Start Celery Beat (periodic task scheduler)
celery -A e_commerce_api beat -l info

# Start both with Gevent pool (better performance)
celery -A e_commerce_api worker -l info -P gevent -c 1000
```

### Common Celery Tasks

#### Email Tasks
```python
# authentication/verification/tasks.py
@shared_task
def send_verification_email(user_email, token):
    """Send email verification link"""
    pass

@shared_task
def send_password_reset_email(user_email, token):
    """Send password reset link"""
    pass
```

#### Transaction Tasks
```python
# transactions/tasks.py
@shared_task
def process_order_payment(order_id):
    """Process payment after order creation"""
    pass

@shared_task
def send_delivery_notification(order_id):
    """Notify customer of delivery"""
    pass

@shared_task
def process_refund(refund_id):
    """Process refund to customer wallet"""
    pass
```

#### User Tasks
```python
# users/tasks.py
@shared_task
def generate_vendor_payouts():
    """Generate daily payouts for vendors"""
    pass

@shared_task
def send_notification_to_user(user_id, title, message):
    """Create and possibly send notification"""
    pass
```

### Monitoring Celery

```bash
# View active tasks
celery -A e_commerce_api inspect active

# View scheduled tasks
celery -A e_commerce_api inspect scheduled

# View statistics
celery -A e_commerce_api inspect stats

# Purge all tasks
celery -A e_commerce_api purge
```

---

## 🛠️ API Endpoints Summary

### API Base URL
```
http://localhost:8000 (Development)
https://api.dandelionz.com.ng (Production)
```

### Authentication Endpoints
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `POST` | `/auth/register/` | Register new user | ❌ |
| `POST` | `/auth/login/` | Login and get tokens | ❌ |
| `POST` | `/auth/token/refresh/` | Refresh access token | ❌ |
| `POST` | `/auth/token/validate/` | Validate token | ✅ |
| `POST` | `/auth/logout/` | Logout | ✅ |
| `POST` | `/auth/email-verify/` | Verify email with token | ❌ |
| `POST` | `/auth/send-verification/` | Send verification email | ✅ |
| `POST` | `/auth/check-verification/` | Check if email verified | ✅ |
| `POST` | `/auth/password-reset/` | Request password reset | ❌ |
| `POST` | `/auth/password-reset/confirm/` | Confirm password reset | ❌ |

### Product Endpoints
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `GET` | `/store/products/` | List all approved products (paginated) | ❌ |
| `GET` | `/store/products/filtered/` | Filter products by category, price, rating | ❌ |
| `GET` | `/store/products/stats/` | Product statistics | ❌ |
| `GET` | `/store/products/summary/` | Product summary view | ❌ |
| `POST` | `/store/products/create/` | Create new product (Vendor) | ✅ |
| `GET` | `/store/products/<slug>/` | Get product details | ❌ |
| `PUT` | `/store/products/<slug>/` | Update product (Owner only) | ✅ |
| `PATCH` | `/store/products/<slug>/patch/` | Partial update product | ✅ |
| `DELETE` | `/store/products/<slug>/delete/` | Delete product (Owner only) | ✅ |

### Cart & Favorites Endpoints
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `GET` | `/store/cart/` | Get user's cart with items | ✅ |
| `POST` | `/store/cart/add/` | Add item to cart | ✅ |
| `PATCH` | `/store/cart/update/` | Set item quantity (accepts `slug` & `quantity`; `quantity=0` removes item) | ✅ |
| `DELETE` | `/store/cart/remove/<slug>/` | Remove item from cart | ✅ |
| `GET` | `/store/favourites/` | List user's favorite products | ✅ |
| `POST` | `/store/favourites/add/` | Add product to favorites | ✅ |
| `DELETE` | `/store/favourites/remove/<slug>/` | Remove from favorites | ✅ |

### Orders & Transactions
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `GET` | `/transactions/orders/` | List user's orders (paginated) | ✅ |
| `POST` | `/transactions/orders/` | Create new order from cart | ✅ |
| `GET` | `/transactions/orders/<order_id>/` | Get order details | ✅ |
| `PUT` | `/transactions/orders/<order_id>/` | Update order (Status tracking) | ✅ |
| `DELETE` | `/transactions/orders/<order_id>/` | Delete order (draft only) | ✅ |
| `GET` | `/transactions/orders/<order_id>/receipt/` | Get order receipt | ✅ |
| `POST` | `/transactions/checkout/` | Initialize payment (Paystack) | ✅ |
| `POST` | `/transactions/verify-payment/` | Verify payment with Paystack reference | ✅ |
| `POST` | `/transactions/webhook/` | Paystack webhook (system) | ❌ |

### User Profiles
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `GET` | `/user/profile/` | Get user profile | ✅ |
| `PUT` | `/user/profile/` | Update user profile | ✅ |
| `PATCH` | `/user/profile/` | Partial update profile | ✅ |
| `POST` | `/user/profile/change-password/` | Change password | ✅ |
| `GET` | `/user/notifications/` | Get user notifications (paginated) | ✅ |
| `POST` | `/user/notifications/<id>/mark-read/` | Mark notification as read | ✅ |
| `GET` | `/user/notifications/unread-count/` | Get unread notification count | ✅ |

### Vendor Profile Endpoints
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `GET` | `/user/vendor/` | Get vendor profile | ✅ |
| `PUT` | `/user/vendor/` | Update vendor profile | ✅ |
| `PATCH` | `/user/vendor/` | Partial update vendor | ✅ |
| `GET` | `/user/vendor/stats/` | Get vendor statistics | ✅ |
| `GET` | `/user/vendor/earnings/` | Get vendor earnings | ✅ |
| `POST` | `/user/vendor/payout/` | Request vendor payout | ✅ |
| `GET` | `/user/vendor/orders/` | Get vendor's orders | ✅ |

### Admin Endpoints
| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---|
| `GET` | `/user/admin/vendors/` | List vendors with filters (Admin) | ✅ |
| `GET` | `/user/admin/vendors/<id>/` | Get vendor details (Admin) | ✅ |
| `PUT` | `/user/admin/vendors/<id>/approve/` | Approve vendor (Admin) | ✅ |
| `PUT` | `/user/admin/vendors/<id>/reject/` | Reject vendor (Admin) | ✅ |
| `GET` | `/user/admin/orders/` | List all orders (Admin) | ✅ |
| `GET` | `/user/admin/orders/<order_id>/` | Get order details (Admin) | ✅ |
| `GET` | `/user/admin/analytics/dashboard/` | Dashboard metrics (Admin) | ✅ |
| `GET` | `/user/admin/analytics/sales/` | Sales analytics (Admin) | ✅ |
| `GET` | `/user/admin/analytics/users/` | User analytics (Admin) | ✅ |

---

## 📊 Database Models - Complete Reference

### CustomUser Model (authentication/models.py)

**Roles:**
- `ADMIN` - Platform administrator
- `BUSINESS_ADMIN` - Business staff with specific permissions
- `VENDOR` - Store owner
- `CUSTOMER` - Regular customer
- `DELIVERY_AGENT` - Delivery personnel

**Status:**
- `ACTIVE` - Account is active
- `SUSPENDED` - Account suspended by admin

**Fields:**
```python
uuid                    # UUID Primary Key (editable=False)
email                   # EmailField (unique)
full_name              # CharField (max 150)
phone_number           # CharField (max 15, optional)
profile_picture        # CloudinaryField (optional)
role                   # Choice field (default: CUSTOMER)
referral_code          # CharField (unique, auto-generated 12-char)
status                 # Choice: ACTIVE, SUSPENDED (default: ACTIVE)
is_verified            # Boolean (email verification status)
is_active              # Boolean (default: True)
is_staff               # Boolean (for admin access)
created_at             # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

**Key Methods:**
- `_generate_unique_referral_code()` - Generates 12-char unique codes
- `is_admin`, `is_business_admin`, `is_vendor`, `is_customer`, `is_delivery_agent` - Role properties

---

### Category Model (store/models.py)

**Fields:**
```python
name                    # CharField (unique)
slug                    # SlugField (unique, auto-generated)
description            # TextField (optional)
image                  # CloudinaryField (optional)
is_active              # Boolean (default: True)
created_at             # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

**Properties:**
- `product_count` - Count of approved submitted products
- `total_sales` - Total sales quantity from category products

---

### Product Model (store/models.py)

**Approval Status:**
- `pending` - Awaiting admin approval
- `approved` - Admin approved
- `rejected` - Admin rejected

**Publish Status:**
- `draft` - Not submitted
- `submitted` - Submitted for approval

**Fields:**
```python
uuid                    # UUIDField (unique, db_indexed)
store (Vendor FK)      # ForeignKey to Vendor
category (Category FK) # ForeignKey to Category
name                    # CharField (max 255)
slug                    # SlugField (unique, auto-generated)
description            # TextField
price                  # DecimalField(10,2)
discounted_price       # DecimalField(10,2) (optional)
stock                  # PositiveIntegerField
image                  # CloudinaryField (deprecated, use ProductImage)
brand                  # CharField (optional)
tags                   # TextField (comma-separated or JSON)
variants               # JSONField (color/size options as JSON)
publish_status         # Choice: draft, submitted (default: draft)
approval_status        # Choice: pending, approved, rejected
approved_by (User FK)  # ForeignKey to CustomUser (who approved)
approval_date          # DateTimeField (when approved)
rejection_reason       # TextField (if rejected)
created_at             # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

**Properties:**
- `in_stock` - Boolean (stock > 0)
- `has_main_image` - Check if main image exists
- `main_image` - Get ProductImage marked as main
- `all_images` - Get all ProductImages ordered
- `video` - Get first ProductVideo

---

### ProductImage Model (store/models.py)

**Fields:**
```python
product (Product FK)   # ForeignKey to Product
image                  # CloudinaryField (required)
is_main                # Boolean (default: False, primary image)
alt_text               # CharField (accessibility text, optional)
variant_association    # JSONField (e.g., {"colors": ["red"]}, optional)
display_order          # PositiveIntegerField (for ordering)
uploaded_at            # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

**Constraints:**
- Unique: (product, image)
- Auto-sets is_main=False on other images when setting one as main

---

### ProductVideo Model (store/models.py)

**Fields:**
```python
product (Product FK)   # ForeignKey to Product
video                  # CloudinaryField (video resource type)
title                  # CharField (optional)
description            # TextField (optional)
duration               # PositiveIntegerField (seconds, optional)
file_size              # PositiveIntegerField (bytes, optional)
uploaded_at            # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

---

### Cart & CartItem Models (store/models.py)

**Cart Fields:**
```python
customer (User FK)     # ForeignKey to CustomUser
created_at             # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

**CartItem Fields:**
```python
cart (Cart FK)         # ForeignKey to Cart
product (Product FK)   # ForeignKey to Product
quantity               # PositiveIntegerField
```

**Cart Properties:**
- `total` - Sum of all item subtotals

---

### Review Model (store/models.py)

**Fields:**
```python
product (Product FK)   # ForeignKey to Product
customer (User FK)     # ForeignKey to CustomUser
rating                 # PositiveIntegerField (1-5+)
comment                # TextField
created_at             # DateTimeField (auto_now_add)
```

---

### Favourite Model (store/models.py)

**Fields:**
```python
customer (User FK)     # ForeignKey to CustomUser
product (Product FK)   # ForeignKey to Product
added_at               # DateTimeField (auto_now_add)
```

**Constraints:**
- Unique: (customer, product)

---

### Order Model (transactions/models.py)

**Status:**
- `PENDING` - Order created
- `PAID` - Payment confirmed
- `SHIPPED` - Order shipped
- `DELIVERED` - Order delivered
- `CANCELED` - Order canceled

**Fields:**
```python
order_id               # UUIDField (unique)
customer (User FK)     # ForeignKey to CustomUser
status                 # Choice (default: PENDING)
total_price            # DecimalField(12,2)
delivery_fee           # DecimalField(10,2) (default: 0)
discount               # DecimalField(10,2) (default: 0)
tracking_number        # CharField (optional)
payment_status         # CharField (UNPAID/PAID)
assigned_at            # DateTimeField (delivery agent assignment)
shipped_at             # DateTimeField
delivered_at           # DateTimeField
returned_at            # DateTimeField
ordered_at             # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

**Methods:**
- `calculate_total()` - Returns: subtotal - discount + delivery_fee
- `update_total()` - Updates total_price field
- Properties: `subtotal`, `total_with_delivery`, `is_paid`, `is_delivered`

---

### OrderItem Model (transactions/models.py)

**Fields:**
```python
order (Order FK)       # ForeignKey to Order
product (Product FK)   # ForeignKey to Product
quantity               # PositiveIntegerField
price_at_purchase      # DecimalField(10,2) (snapshot of price)
```

**Properties:**
- `item_subtotal` - price_at_purchase × quantity
- `vendor` - Gets product.store

---

### OrderStatusHistory Model (transactions/models.py)

**Changed By:**
- `ADMIN` - Administrator changed status
- `SYSTEM` - Automatic/system change
- `VENDOR` - Vendor changed status
- `CUSTOMER` - Customer initiated change

**Fields:**
```python
order (Order FK)       # ForeignKey to Order
status                 # Choice (PENDING/PAID/SHIPPED/DELIVERED/CANCELED)
changed_by             # Choice (ADMIN/SYSTEM/VENDOR/CUSTOMER)
admin (User FK)        # ForeignKey to CustomUser (who changed it)
reason                 # TextField (reason for change)
changed_at             # DateTimeField (default: now())
```

---

### Payment Model (transactions/models.py)

**Status:**
- `PENDING` - Payment initiated
- `SUCCESS` - Payment successful
- `FAILED` - Payment failed

**Fields:**
```python
order (Order OneToOne) # OneToOneField to Order
reference              # CharField (unique, Paystack reference)
amount                 # DecimalField(10,2)
status                 # Choice (default: PENDING)
gateway                # CharField (default: 'Paystack')
paid_at                # DateTimeField (when payment succeeded)
verified               # Boolean (payment verified, default: False)
created_at             # DateTimeField (auto_now_add)
```

**Methods:**
- `mark_as_successful()` - Sets status=SUCCESS, verified=True, paid_at=now()

---

### Wallet Model (transactions/models.py)

**Fields:**
```python
user (User OneToOne)   # OneToOneField to CustomUser
balance                # DecimalField(12,2) (default: 0)
updated_at             # DateTimeField (auto_now)
```

**Methods:**
- `credit(amount, source)` - Add funds + creates WalletTransaction
- `debit(amount, source)` - Subtract funds + creates WalletTransaction (validates balance)

---

### WalletTransaction Model (transactions/models.py)

**Type:**
- `CREDIT` - Funds received
- `DEBIT` - Funds withdrawn

**Fields:**
```python
wallet (Wallet FK)     # ForeignKey to Wallet
transaction_type       # Choice (CREDIT/DEBIT)
amount                 # DecimalField(10,2)
source                 # CharField (reason/source)
created_at             # DateTimeField (auto_now_add)
```

---

### ShippingAddress Model (transactions/models.py)

**Fields:**
```python
order (Order OneToOne) # OneToOneField to Order
full_name              # CharField
address                # TextField
city                   # CharField
state                  # CharField
country                # CharField
postal_code            # CharField
phone_number           # CharField
```

---

### Refund Model (transactions/models.py)

**Status:**
- `PENDING` - Refund requested
- `APPROVED` - Refund approved
- `REJECTED` - Refund rejected
- `COMPLETED` - Refund processed

**Fields:**
```python
order (Order FK)       # ForeignKey to Order
reason                 # TextField (refund reason)
amount                 # DecimalField(10,2)
status                 # Choice (default: PENDING)
created_at             # DateTimeField (auto_now_add)
updated_at             # DateTimeField (auto_now)
```

---

### InstallmentPlan Model (transactions/models.py)

**Fields:**
```python
order (Order OneToOne) # OneToOneField to Order
total_amount           # DecimalField(10,2)
installment_count      # PositiveIntegerField (number of payments)
installment_amount     # DecimalField(10,2) (per installment)
```

---

### Vendor Model (users/models.py)

**Vendor Status:**
- `pending` - Awaiting approval
- `approved` - Approved vendor
- `rejected` - Rejected vendor
- `suspended` - Suspended vendor

**Fields:**
```python
user (User OneToOne)   # OneToOneField to CustomUser
store_name             # CharField (default: "Unnamed Store")
store_description      # TextField
business_registration_number # CharField (max 50)
address                # CharField (max 255)
bank_name              # CharField (max 100)
account_number         # CharField (max 20)
recipient_code         # CharField (Paystack recipient code)
is_verified_vendor     # Boolean (default: False)
vendor_status          # Choice (default: pending)
```

---

### Customer Model (users/models.py)

**Fields:**
```python
user (User OneToOne)   # OneToOneField to CustomUser
shipping_address       # TextField
city                   # CharField
country                # CharField
postal_code            # CharField (max 20)
loyalty_points         # PositiveIntegerField (default: 0)
```

---

### BusinessAdmin Model (users/models.py)

**Fields:**
```python
user (User OneToOne)   # OneToOneField to CustomUser
position               # CharField (role description, max 100)
can_manage_vendors     # Boolean (default: True)
can_manage_orders      # Boolean (default: True)
can_manage_payouts     # Boolean (default: True)
can_manage_inventory   # Boolean (default: True)
```

---

### DeliveryAgent Model (users/models.py)

**Fields:**
```python
user (User OneToOne)   # OneToOneField to CustomUser
phone                  # CharField
is_active              # Boolean (default: True)
created_at             # DateTimeField (auto_now_add)
```

---

### Notification Model (users/models.py)

**Fields:**
```python
recipient (User FK)    # ForeignKey to CustomUser
title                  # CharField
message                # TextField
is_read                # Boolean (default: False)
created_at             # DateTimeField (auto_now_add)
```

**Methods:**
- `mark_as_read()` - Sets is_read=True

---

## ✅ Feature Checklist

### Core Features
- ✅ Multi-vendor marketplace
- ✅ User role management (5 roles)
- ✅ JWT authentication with refresh tokens
- ✅ Email verification workflow
- ✅ Referral system with unique codes
- ✅ Product catalog with categories
- ✅ Draft & approval workflow for products
- ✅ Multiple product images & videos
- ✅ Product variants (JSON-based)
- ✅ Shopping cart management
- ✅ Favorites/wishlist
- ✅ Product reviews & ratings
- ✅ Order management with status tracking
- ✅ Order status history logging
- ✅ Paystack payment integration
- ✅ Payment webhook handling
- ✅ Installment payment plans
- ✅ Refund management system
- ✅ User wallets with transactions
- ✅ Order receipts

### Admin Features
- ✅ User management
- ✅ Vendor approval/rejection
- ✅ Product approval workflow
- ✅ Order management
- ✅ Finance/payout processing
- ✅ Analytics dashboard
- ✅ Marketplace statistics
- ✅ Vendor analytics
- ✅ User analytics
- ✅ Sales analytics

### User Features
- ✅ Profile management
- ✅ Password change
- ✅ Vendor profiles with earnings
- ✅ Delivery agent profiles
- ✅ Notification system
- ✅ Unread notification count
- ✅ Notification read status

### Technical Features
- ✅ Celery async task processing
- ✅ Celery Beat periodic tasks
- ✅ Redis caching
- ✅ Cloudinary image/video storage
- ✅ PostgreSQL database
- ✅ Docker containerization
- ✅ Swagger/OpenAPI documentation
- ✅ CORS configuration
- ✅ Rate limiting
- ✅ Admin interface security
- ✅ Email sending with retry logic
- ✅ Transaction logging

---

## 🐛 Troubleshooting

### Common Issues & Solutions

#### 1. Database Connection Error
```
Error: could not connect to server
Solution:
- Ensure PostgreSQL is running: docker-compose up db
- Check DB_HOST, DB_USER, DB_PASSWORD in .env
- Test connection: docker-compose exec db psql -U postgres
```

#### 2. Redis Connection Failed
```
Error: ConnectionError: Error 111 connecting to 127.0.0.1:6379
Solution:
- Start Redis: docker-compose up redis
- Check REDIS_URL in .env (should be redis://redis:6379/0)
- Test connection: docker-compose exec redis redis-cli ping
```

#### 3. Email Verification Timeout
```
Error: EmailException - Timeout waiting for SMTP response
Solution:
- Check EMAIL_TIMEOUT setting (default: 60 seconds)
- Verify EMAIL_HOST and EMAIL_PORT are correct
- Check firewall/network access to SMTP server
- Review EMAIL_CONNECTION_RETRY_ATTEMPTS setting
```

#### 4. Celery Tasks Not Running
```
Error: Task not executing
Solution:
- Ensure Celery worker is running: celery -A e_commerce_api worker -l info
- Check CELERY_BROKER_URL points to Redis
- Verify tasks are imported in worker: celery -A e_commerce_api inspect active
- Check task logs: celery -A e_commerce_api events
```

#### 5. Static Files Not Loading
```
Error: 404 on /static/ URLs in production
Solution:
- Collect static files: python manage.py collectstatic --noinput
- Check STATIC_URL and STATIC_ROOT in settings
- Verify WhiteNoise middleware is enabled
- Check STATICFILES_STORAGE setting
```

#### 6. Payment Processing Fails
```
Error: Paystack webhook not received or payment not marked as paid
Solution:
- Verify PAYSTACK_SECRET_KEY is correct
- Check webhook signature validation in paystack.py
- Ensure PAYSTACK_WEBHOOK_URL is publicly accessible
- Test webhook: curl -X POST https://api.dandelionz.com.ng/transactions/paystack/webhook/
- Check transaction logs for error details
```

#### 7. Migration Issues
```
Error: No such table / Migration conflicts
Solution:
- Create new migration: python manage.py makemigrations
- Apply migrations: python manage.py migrate
- Check for conflicting migration files in migrations/
- If stuck: python manage.py migrate --fake-initial
```

#### 8. Vendor Account Not Found
```
Error: Vendor profile does not exist
Solution:
- Ensure Vendor profile is created via signals on user creation
- Manually create: Vendor.objects.create(user=user, store_name="Store")
- Check signals.py for proper connection to post_save
```

---

## 📞 Support & Contributions

For issues, feature requests, or contributions:

1. **Report Issues**: Create a GitHub issue with detailed error logs
2. **Feature Requests**: Describe the feature and expected behavior
3. **Pull Requests**: Follow code style and include tests
4. **Documentation**: Update README for any API changes

---

## 📄 License

This project is proprietary software owned by Dandelionz. All rights reserved.

---

**Last Updated**: January 2026  
**API Version**: 1.0.0  
**Maintainer**: Development Team

#### 5. Email Not Sending
```
Error: SMTPAuthenticationError
Solution:
- Use Gmail app password (not account password)
- Enable "Less secure apps" if using Gmail
- Check EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
```

---

## 🤝 Contributing

### Code Style

Follow PEP 8:
```bash
# Check code style
flake8 .

# Auto-format code
black .

# Check imports
isort .
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/feature-name

# Make commits
git add .
git commit -m "feat: Add new feature"

# Push and create PR
git push origin feature/feature-name
```

### Commit Message Format

```
type: subject (max 50 chars)

body (max 72 chars per line)

footer
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

---

## 📝 API Documentation

Interactive API documentation available at:

- **Swagger UI**: `/swagger/`
- **ReDoc**: `/redoc/`
- **OpenAPI JSON**: `/swagger.json/`
- **OpenAPI YAML**: `/swagger.yaml/`

All endpoints are fully documented with:
- Request/response schemas
- Parameter descriptions
- Example values
- Status codes

---

## 📄 License

This project is proprietary and not for distribution.

---

## 👥 Support

For issues, feature requests, or questions:

- **Email**: dandelionsuperglobal.ltd@gmail.com
- **Documentation**: https://dandelionz.net/docs/
- **Terms**: https://dandelionz.net/terms/

---

## 🎯 Future Enhancements

- [ ] Mobile app (iOS/Android)
- [ ] Real-time notifications (WebSocket)
- [ ] Merchant analytics dashboard
- [ ] Inventory management system
- [ ] Review moderation system
- [ ] Subscription products
- [ ] Advanced search with Elasticsearch
- [ ] Multi-currency support
- [ ] Split payments
- [ ] Loyalty rewards program

---

**Last Updated**: January 8, 2026  
**Project Version**: 1.0.0  
**API Version**: v1
