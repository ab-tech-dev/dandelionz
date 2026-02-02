# Vendor & Customer Withdrawal Flow Documentation

## Overview
This document outlines the complete withdrawal flow for vendors and customers in the e-commerce API. The system handles withdrawal requests with proper validation, wallet management, admin notifications, and approval workflows.

---

## 1. Flow Architecture

### High-Level Flow
```
User submits withdrawal request
    ↓
Validate PIN + Balance
    ↓
Create PayoutRequest + Debit Wallet
    ↓
Send Admin Notification
    ↓
Admin approves/rejects
    ↓
Notify User of approval/rejection
    ↓
Process payout (via payment provider)
```

---

## 2. Key Components

### 2.1 Models

#### PayoutRequest Model
Located in: `users/models.py`

**Purpose:** Tracks all withdrawal requests from vendors and customers

**Fields:**
- `id`: Unique identifier
- `vendor`: Foreign key to Vendor (null for customer withdrawals)
- `user`: Foreign key to CustomUser (null for vendor withdrawals)
- `amount`: Withdrawal amount in decimal
- `status`: pending, processing, successful, failed, cancelled
- `bank_name`: Bank name for transfer
- `account_number`: Account number
- `account_name`: Account holder name
- `recipient_code`: Payment provider code
- `reference`: Unique reference (WTH-XXXXXXXXXX)
- `created_at`: Request timestamp
- `processed_at`: Processing/completion timestamp
- `failure_reason`: Reason for failure if failed

**Status Flow:**
```
pending → processing → successful (or failed/cancelled)
```

#### PaymentPIN Model
Located in: `users/models.py`

**Purpose:** Stores hashed PIN for withdrawal authorization

**Fields:**
- `user`: OneToOne to CustomUser
- `pin_hash`: Hashed PIN (never stored as plain text)
- `is_default`: Boolean flag for default PIN (0000)
- `created_at`, `updated_at`: Timestamps

**Security Features:**
- PIN is hashed using Django's `make_password()`
- Default PIN (0000) cannot be used for withdrawals
- Users must set a custom PIN before withdrawing

#### Wallet Model
Located in: `transactions/models.py`

**Purpose:** Manages user balance

**Methods:**
- `credit(amount)`: Add funds
- `debit(amount)`: Remove funds with balance validation

---

### 2.2 Services

#### PayoutService
Located in: `users/services/payout_service.py`

**Key Methods:**

##### `validate_withdrawal_request(user, amount)`
Validates withdrawal before processing
- Returns: `(is_valid: bool, error_message: str)`
- Checks:
  - Wallet has sufficient balance
  - Amount > 0
  - PIN is configured and not default

```python
is_valid, error_msg = PayoutService.validate_withdrawal_request(user, amount)
if not is_valid:
    return error_response(error_msg)
```

##### `verify_pin(user, pin)`
Verifies user's payment PIN
- Returns: `(is_valid: bool, error_message: str)`
- Uses Django's `check_password()` for secure comparison

```python
pin_valid, error = PayoutService.verify_pin(user, pin)
if not pin_valid:
    return error_response(error)
```

##### `create_withdrawal_request(...)`
Creates withdrawal request and notifies admins
- **Transaction-safe:** Uses `@transaction.atomic`
- **Returns:** `(PayoutRequest or None, error_message)`
- **Steps:**
  1. Validate amount
  2. Check balance
  3. Create PayoutRequest
  4. Debit wallet
  5. Send admin notifications
  6. Log transaction

```python
payout, error = PayoutService.create_withdrawal_request(
    user=request.user,
    amount=amount,
    bank_name=bank_name,
    account_number=account_number,
    account_name=account_name,
    vendor=vendor  # None for customers
)
```

##### `notify_admins_of_withdrawal(payout, user, vendor)`
Sends notifications to all admins
- **Channel:** WebSocket + Email
- **Priority:** High for amounts > ₦100,000
- **Content:** Withdrawal details, requestor info, reference number
- **Metadata:** Includes withdrawal ID, reference, amount for tracking

```python
NotificationService.create_notification(
    user=admin.user,
    title="New Vendor Withdrawal Request",
    message=f"{vendor_name} has requested withdrawal of ₦{amount:,.2f}",
    category='withdrawal',
    priority='high',
    send_websocket=True,
    send_email=True,
)
```

---

### 2.3 Views & Endpoints

#### Vendor Withdrawal Endpoint
**Endpoint:** `POST /api/vendor/wallet/request-withdrawal/`
**View:** `VendorViewSet.request_withdrawal()`
**Permission:** Vendor only (IsAuthenticated + vendor check)

**Request Body:**
```json
{
    "amount": 50000.00,
    "pin": "1234"
}
```

**Response (Success):**
```json
{
    "success": true,
    "message": "Withdrawal request of ₦50,000.00 is being processed. Reference: WTH-ABC123DEF456",
    "reference": "WTH-ABC123DEF456"
}
```

**Response (Error):**
```json
{
    "success": false,
    "message": "Invalid PIN" / "Insufficient balance" / "PIN not configured"
}
```

#### Customer Withdrawal Endpoint
**Endpoint:** `POST /api/customer/wallet/request-withdrawal/`
**View:** `CustomerWalletViewSet.request_withdrawal()`
**Permission:** Customer only

**Request Body:**
```json
{
    "amount": 10000.00,
    "pin": "1234",
    "bank_name": "GTBank",
    "account_number": "0123456789",
    "account_name": "John Doe"
}
```

**Key Difference:** Customers must provide bank details (vendors use saved profile info)

#### Admin Withdrawal Management Endpoints

##### List All Withdrawals
**Endpoint:** `GET /api/admin/finance/list-withdrawals/`
**Query Parameters:**
- `status`: pending, processing, successful, failed, cancelled
- `type`: vendor, customer, all

**Response:**
```json
{
    "success": true,
    "count": 15,
    "data": [
        {
            "id": "uuid",
            "reference": "WTH-ABC123DEF456",
            "amount": "50000.00",
            "requestor_name": "Tech Store",
            "requestor_email": "vendor@example.com",
            "requestor_type": "Vendor",
            "status": "pending",
            "bank_name": "GTBank",
            "account_number": "0123456789",
            "account_name": "Tech Store Ltd",
            "created_at": "2025-02-02T10:30:00Z",
            "processed_at": null,
            "failure_reason": null
        }
    ]
}
```

##### Get Withdrawal Details
**Endpoint:** `GET /api/admin/finance/withdrawal-detail/?id=<withdrawal_id>`
**Response:** Single withdrawal object with all details

##### Approve Withdrawal
**Endpoint:** `POST /api/admin/finance/approve-withdrawal/`
**Request Body:**
```json
{
    "withdrawal_id": "uuid",
    "notes": "Approved for processing"
}
```

**Actions:**
1. Update status to "processing"
2. Record processed_at timestamp
3. Send notification to requestor: "Your withdrawal has been approved"
4. Prepare for actual payment provider transfer

##### Reject Withdrawal
**Endpoint:** `POST /api/admin/finance/reject-withdrawal/`
**Request Body:**
```json
{
    "withdrawal_id": "uuid",
    "reason": "Account verification failed"
}
```

**Actions:**
1. Update status to "failed"
2. Record rejection reason
3. Refund amount to wallet: `wallet.credit(amount)`
4. Send notification to requestor with reason

---

## 3. Complete Withdrawal Flow - Step by Step

### Step 1: User Initiates Withdrawal
```python
# Vendor/Customer calls withdrawal endpoint
POST /api/vendor/wallet/request-withdrawal/
{
    "amount": 50000.00,
    "pin": "1234"
}
```

### Step 2: Validation in View
```python
def request_withdrawal(self, request):
    # 1. Get user profile (vendor/customer)
    vendor = self.get_vendor(request)
    
    # 2. Deserialize and validate input
    serializer = WithdrawalRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    # 3. Call PayoutService for complete validation
    is_valid, error_msg = PayoutService.validate_withdrawal_request(
        request.user, 
        serializer.validated_data['amount']
    )
    
    # 4. Verify PIN
    pin_valid, error = PayoutService.verify_pin(
        request.user, 
        serializer.validated_data['pin']
    )
```

### Step 3: Create Withdrawal & Notify Admin
```python
# PayoutService.create_withdrawal_request() is transaction-safe
payout, error = PayoutService.create_withdrawal_request(
    user=request.user,
    amount=amount,
    bank_name=vendor.bank_name,
    account_number=vendor.account_number,
    account_name=vendor.account_name,
    recipient_code=vendor.recipient_code,
    vendor=vendor
)

# Within create_withdrawal_request():
# 1. Create PayoutRequest object with status='pending'
# 2. Debit wallet immediately
# 3. Call notify_admins_of_withdrawal() → sends WebSocket + Email
# 4. Log transaction
```

### Step 4: Admin Notifications
Admins receive notification:
```
Title: "New Vendor Withdrawal Request"
Message: "Tech Store has requested a withdrawal of ₦50,000.00"
Details:
  - Requestor: Tech Store (vendor@example.com)
  - Amount: ₦50,000.00
  - Bank: GTBank
  - Account: 0123456789
  - Reference: WTH-ABC123DEF456
  - Action: Review Withdrawal (link to /admin/withdrawals/{id})
```

### Step 5: Admin Review & Action
Admin can:
- **Approve:** Call `approve_withdrawal(withdrawal_id)` → status: "processing" + user notified
- **Reject:** Call `reject_withdrawal(withdrawal_id, reason)` → refund + user notified

### Step 6: User Receives Update
Upon approval:
```
Title: "Withdrawal Approved"
Message: "Your withdrawal of ₦50,000.00 has been approved and is being processed"
```

Upon rejection:
```
Title: "Withdrawal Rejected"
Message: "Your withdrawal has been rejected"
Details: Reason provided + Amount refunded to wallet
```

---

## 4. Validation Rules

### PIN Validation
✅ **Required:**
- PIN must be 4 digits
- PIN must not be default (0000)
- PIN must match stored hash

### Balance Validation
✅ **Required:**
- Wallet balance ≥ requested amount
- Amount > 0

### For Vendors
✅ **Required:**
- Bank name set in profile
- Account number set in profile
- Account name set in profile

### For Customers
✅ **Required:**
- Bank name in request
- Account number in request
- Account name in request

---

## 5. Error Handling

### Common Errors

| Error | Status | Cause | Solution |
|-------|--------|-------|----------|
| "PIN not configured" | 400 | User never set PIN | User must set PIN first |
| "Insufficient balance" | 400 | Balance < amount | User must wait for more earnings |
| "Invalid PIN" | 400 | Wrong PIN entered | User re-enters correct PIN |
| "Bank details required" | 400 | Missing bank info | User updates payment settings |
| "Cannot approve/reject" | 400 | Wrong status | Withdrawal already processed |

### Transaction Safety
All operations use `@transaction.atomic` to ensure:
- Either complete success or complete rollback
- Wallet is debited only after PayoutRequest created
- Notifications sent only after successful request creation

---

## 6. Security Considerations

### PIN Security
✅ **Hash-based:** Using Django's PBKDF2 hashing
✅ **Default protection:** Can't use default (0000) for withdrawals
✅ **User-controlled:** Only user can set/change their PIN

### Amount Validation
✅ **Decimal precision:** Using `Decimal` type for financial calculations
✅ **Balance check:** Real-time balance verification
✅ **Wallet audit trail:** All transactions logged in `WalletTransaction`

### Admin Authorization
✅ **Permission check:** Only admins can approve/reject
✅ **Audit trail:** Who approved, when, notes recorded

---

## 7. Database Indexes & Performance

### Optimized Queries
```python
# Fast lookup by reference
PayoutRequest.objects.get(reference='WTH-ABC123')

# Fast filtering by status
PayoutRequest.objects.filter(status='pending')

# Fast filtering by vendor
PayoutRequest.objects.filter(vendor=vendor, status='processing')

# Ordered by most recent
PayoutRequest.objects.all().order_by('-created_at')
```

### Database Indexes (from model Meta class)
```python
indexes = [
    models.Index(fields=['vendor', 'status']),
    models.Index(fields=['user', 'status']),
]
```

---

## 8. Future Enhancements

### Payment Provider Integration
- [ ] Integrate with Paystack/Flutterwave for real transfers
- [ ] Webhook handling for payment confirmation
- [ ] Automatic status update from provider

### Scheduled Processing
- [ ] Use Celery to batch process approvals
- [ ] Scheduled task to mark successful after provider confirmation
- [ ] Automatic retry on provider failure

### Enhanced Notifications
- [ ] SMS notifications for high-value withdrawals
- [ ] Push notifications for mobile app
- [ ] Email with transaction receipt

### Compliance & Reporting
- [ ] KYC verification before withdrawal
- [ ] Withdrawal limits based on verification level
- [ ] Tax/compliance reporting integration
- [ ] Fraud detection system

### Analytics
- [ ] Withdrawal velocity analysis
- [ ] Suspicious pattern detection
- [ ] Vendor payout analytics
- [ ] Commission calculation history

---

## 9. Testing Checklist

### Unit Tests
- [ ] `test_validate_withdrawal_request()` with various amounts
- [ ] `test_verify_pin()` with correct/incorrect PINs
- [ ] `test_create_withdrawal_request()` with success/failure
- [ ] `test_notify_admins()` notification creation

### Integration Tests
- [ ] End-to-end vendor withdrawal flow
- [ ] End-to-end customer withdrawal flow
- [ ] Admin approval workflow
- [ ] Admin rejection workflow
- [ ] Wallet refund on rejection

### Edge Cases
- [ ] Attempt withdrawal with insufficient balance
- [ ] Attempt withdrawal without PIN configured
- [ ] Attempt withdrawal with default PIN
- [ ] Attempt to approve/reject non-existent withdrawal
- [ ] Attempt to approve/reject already processed withdrawal
- [ ] Concurrent withdrawal requests (race condition test)

---

## 10. Troubleshooting Guide

### "PIN not configured" Error
**Cause:** User never set a PIN
**Solution:** 
1. User calls `POST /api/vendor/payment-settings/set-pin/`
2. Provide `pin` and `confirm_pin`
3. Retry withdrawal

### "Insufficient balance" Error
**Cause:** Wallet balance < withdrawal amount
**Solution:**
1. User waits for more orders/referrals
2. Check pending balance: `GET /api/vendor/wallet/`
3. Try with smaller amount

### "Invalid PIN" Error
**Cause:** Wrong PIN entered
**Solution:**
1. User re-enters correct PIN
2. If forgotten, user must reset via forgot-pin endpoint (if available)
3. Admin can manually reset if needed

### Withdrawal Stuck in "Processing"
**Cause:** Payment provider integration pending
**Solution:**
1. Check admin panel for failure_reason
2. Admin can reject if failed
3. Contact support if urgent

---

## 11. API Summary Table

| Operation | Method | Endpoint | Auth | Body |
|-----------|--------|----------|------|------|
| Request Withdrawal (Vendor) | POST | `/vendor/wallet/request-withdrawal/` | Vendor | amount, pin |
| Request Withdrawal (Customer) | POST | `/customer/wallet/request-withdrawal/` | Customer | amount, pin, bank details |
| List Withdrawals (Admin) | GET | `/admin/finance/list-withdrawals/` | Admin | status, type (query) |
| Get Withdrawal Detail (Admin) | GET | `/admin/finance/withdrawal-detail/` | Admin | id (query) |
| Approve Withdrawal (Admin) | POST | `/admin/finance/approve-withdrawal/` | Admin | withdrawal_id, notes |
| Reject Withdrawal (Admin) | POST | `/admin/finance/reject-withdrawal/` | Admin | withdrawal_id, reason |
| Get Payment Settings (Vendor) | GET | `/vendor/payment-settings/` | Vendor | - |
| Update Payment Settings (Vendor) | POST | `/vendor/update-payment-settings/` | Vendor | bank_name, account_number, account_name |
| Set Payment PIN (Vendor) | POST | `/vendor/set-payment-pin/` | Vendor | pin, confirm_pin |

---

## 12. Code Examples

### Example 1: Vendor Initiates Withdrawal
```python
# Frontend/Client
POST /api/vendor/wallet/request-withdrawal/
Authorization: Bearer <token>
Content-Type: application/json

{
    "amount": 100000.00,
    "pin": "1234"
}

# Response
{
    "success": true,
    "message": "Withdrawal request of ₦100,000.00 is being processed. Reference: WTH-A1B2C3D4E5F6",
    "reference": "WTH-A1B2C3D4E5F6"
}
```

### Example 2: Admin Approves Withdrawal
```python
# Backend (Admin Panel)
POST /api/admin/finance/approve-withdrawal/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
    "withdrawal_id": "550e8400-e29b-41d4-a716-446655440000",
    "notes": "KYC verified, amount confirmed"
}

# Response
{
    "success": true,
    "message": "Withdrawal WTH-A1B2C3D4E5F6 approved and marked for processing"
}

# Vendor receives WebSocket notification
{
    "title": "Withdrawal Approved",
    "message": "Your withdrawal of ₦100,000.00 has been approved",
    "type": "withdrawal_approved"
}
```

### Example 3: Admin Rejects Withdrawal
```python
# Backend (Admin Panel)
POST /api/admin/finance/reject-withdrawal/
Authorization: Bearer <admin_token>
Content-Type: application/json

{
    "withdrawal_id": "550e8400-e29b-41d4-a716-446655440000",
    "reason": "Account number does not match KYC documentation"
}

# Response
{
    "success": true,
    "message": "Withdrawal WTH-A1B2C3D4E5F6 rejected. Amount of ₦100,000.00 refunded to wallet."
}

# Vendor receives notification + ₦100,000 refunded to wallet
# Next wallet balance will include the refunded amount
```

---

## Summary

The withdrawal flow is now fully implemented with:
✅ Secure PIN-based authorization
✅ Real-time balance validation
✅ Admin notifications (WebSocket + Email)
✅ Complete approval/rejection workflow
✅ Wallet refund on rejection
✅ Transaction-safe operations
✅ Comprehensive audit trail
✅ Error handling and validation
✅ Clear API documentation

All withdrawals are tracked with reference numbers and timestamps for complete transparency and compliance.
