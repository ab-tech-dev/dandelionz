# E-Commerce API Platform - Complete Documentation

## 📋 Table of Contents
1. [Overview](#overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [System Architecture](#system-architecture)
5. [Database Models](#database-models)
6. [User Management](#user-management)
7. [Store & Products](#store--products)
8. [Orders & Cart](#orders--cart)
9. [Payments & Transactions](#payments--transactions)
10. [Authentication & Verification](#authentication--verification)
11. [API Endpoints](#api-endpoints)
12. [Setup & Deployment](#setup--deployment)
13. [Development Guide](#development-guide)
14. [Security Features](#security-features)

---

## 🎯 Overview

**Dandelionz** is a comprehensive multi-vendor e-commerce API platform built with Django and Django REST Framework. It enables vendors to list and manage products, customers to browse and purchase items, and administrators to oversee the entire marketplace.

### Key Features:
- **Multi-Vendor Architecture**: Support for multiple vendors managing their own product catalogs
- **Secure Authentication**: JWT-based authentication with email verification
- **Payment Processing**: Paystack integration for secure payment handling
- **Order Management**: Complete order lifecycle from creation to delivery
- **Wallet System**: User wallets with credit/debit transaction tracking
- **Customer Profiles**: Vendor and Customer profile management with specialized features
- **Admin Dashboard**: Business admin controls for vendor management, orders, and payouts
- **Product Management**: Full CRUD operations with categories, reviews, and ratings
- **Shopping Cart**: Add/remove items, manage favorites
- **Email Verification**: Automated email notifications and verification workflows
- **Referral System**: Built-in referral code tracking for user acquisition

---

## 🛠️ Tech Stack

### Backend Framework
- **Django** 5.2.7 - Web framework
- **Django REST Framework** 3.16.1 - API development
- **PostgreSQL** - Primary database
- **Redis** - Caching and message broker

### Key Libraries
- **Django Celery Beat** 2.8.1 - Task scheduling
- **Django Celery Results** 2.6.0 - Task result persistence
- **Simple JWT** 5.5.1 - JWT authentication
- **Cloudinary** 1.44.1 - Image storage and management
- **Paystack** - Payment gateway integration
- **Django CORS Headers** 4.9.0 - Cross-origin request handling
- **DRF YASG** 1.21.11 - Swagger/OpenAPI documentation
- **DRF Spectacular** 0.28.0 - Enhanced API documentation

### Deployment
- **Docker** & **Docker Compose** - Containerization
- **Gunicorn** 23.0.0 - WSGI application server
- **WhiteNoise** 6.11.0 - Static file serving

---

## 📁 Project Structure

```
e_commerce_api/
├── authentication/           # User authentication & verification
│   ├── auth/               # Login, registration, token management
│   ├── verification/       # Email verification, password reset
│   ├── core/              # Base classes, utilities, permissions
│   ├── models.py          # CustomUser model
│   └── serializers.py     # Auth request/response serializers
├── users/                  # User profiles & admin functions
│   ├── models.py          # Vendor, Customer, BusinessAdmin, Notification
│   ├── services/          # Payout, profile resolution
│   ├── views.py           # Profile management, admin analytics
│   └── serializers.py     # User profile serializers
├── store/                  # Products, cart, favorites
│   ├── models.py          # Product, Cart, CartItem, Favorite, Review
│   ├── views.py           # Product listing, cart management
│   └── serializers.py     # Product & cart serializers
├── transactions/           # Orders, payments, wallets
│   ├── models.py          # Order, Payment, Wallet, Refund, InstallmentPlan
│   ├── paystack.py        # Paystack payment gateway integration
│   ├── views.py           # Order & payment processing
│   └── serializers.py     # Order & payment serializers
├── e_commerce_api/        # Project settings & configuration
│   ├── settings.py        # Django settings
│   ├── urls.py            # URL routing
│   ├── celery.py          # Celery configuration
│   └── wsgi.py            # WSGI application
├── templates/             # Email templates
│   └── emails/           # HTML email templates
├── Dockerfile             # Container configuration
├── docker-compose.yml     # Multi-container orchestration
├── requirements.txt       # Python dependencies
└── manage.py             # Django management script
```

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
2. **PAID** → Payment verified (status remains PENDING)
3. **SHIPPED** → Admin/Vendor marks as shipped
4. **DELIVERED** → Delivery agent marks as delivered
5. **CANCELED** → Order canceled (can happen at any stage)

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

## 🐛 Troubleshooting

### Common Issues & Solutions

#### 1. Database Connection Error
```
Error: could not connect to server
Solution:
- Ensure PostgreSQL is running
- Check DB_HOST, DB_USER, DB_PASSWORD in .env
- docker-compose exec db psql -U postgres
```

#### 2. Redis Connection Failed
```
Error: ConnectionError: Error 111 connecting to 127.0.0.1:6379
Solution:
- Start Redis: docker-compose up redis
- Check Redis URL in .env
- redis-cli ping
```

#### 3. Migration Conflicts
```
Error: Conflicting migrations
Solution:
- Check for multiple migration files in same app
- Delete conflicting migrations if not in production
- python manage.py migrate --fake-initial
```

#### 4. Static Files Not Loading
```
Error: 404 on /static/ URLs
Solution:
- python manage.py collectstatic --noinput
- Check STATIC_URL in settings
- Check WhiteNoise configuration
```

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

- **Email**: support@dandelionz.net
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
