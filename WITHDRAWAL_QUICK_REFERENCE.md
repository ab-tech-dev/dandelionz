# Withdrawal Flow - Quick Reference Guide

## 📋 Overview
Complete vendor and customer withdrawal system with admin notifications, approval workflow, and wallet management.

---

## 🔄 Main Flow Diagram

```
User Request Withdrawal
        ↓
   ↙─────────┴─────────╲
PIN Check    Balance    Bank Details
   ↖─────────┬─────────╱
        ↓
Create PayoutRequest
        ↓
Debit Wallet Immediately
        ↓
Send Admin Notifications
  (WebSocket + Email)
        ↓
Admin Reviews/Approves/Rejects
        ↓
  ↙─────────┴─────────╲
Approved         Rejected
  ↓                  ↓
Processing     Refund Wallet
  ↓                  ↓
Pay via Provider  Notify User
  ↓                  ↓
Mark Successful  Status: Failed
  ↓                  ↓
Notify User     Complete
  ↓
Complete
```

---

## 🎯 Key Decision Points

### Should withdrawal be allowed?
```
✓ PIN set and not default (0000)
✓ PIN verified correctly
✓ Wallet balance ≥ requested amount
✓ Amount > 0
✓ For vendors: bank details saved in profile
✓ For customers: bank details provided in request
```

---

## 📱 Endpoints Quick Lookup

### For Vendors
```
POST /api/vendor/wallet/request-withdrawal/
  → Amount, PIN required
  → Uses saved bank details from profile

GET  /api/vendor/payment-settings/
  → View saved bank details

POST /api/vendor/update-payment-settings/
  → Update bank name, account number, account name

POST /api/vendor/set-payment-pin/
  → Set/change withdrawal PIN
```

### For Customers
```
POST /api/customer/wallet/request-withdrawal/
  → Amount, PIN, Bank details all required

POST /api/customer/payment-settings/set-payment-pin/
  → Set/change withdrawal PIN
```

### For Admins
```
GET  /api/admin/finance/list-withdrawals/?status=pending&type=vendor
  → List pending withdrawals

GET  /api/admin/finance/withdrawal-detail/?id=<id>
  → View detailed withdrawal info

POST /api/admin/finance/approve-withdrawal/
  → {withdrawal_id, notes}

POST /api/admin/finance/reject-withdrawal/
  → {withdrawal_id, reason}
```

---

## 🔐 Security Checklist

- ✅ PIN hashed with Django's PBKDF2 (not plain text)
- ✅ Default PIN (0000) cannot be used for withdrawals
- ✅ Real-time balance verification (no overdrafts)
- ✅ All operations transaction-safe (atomic)
- ✅ Wallet debited immediately, before admin approval
- ✅ Rejection refunds entire amount
- ✅ Admin-only approval endpoints
- ✅ Complete audit trail (timestamps, reference numbers)

---

## 💰 Wallet States During Withdrawal

### Before Request
```
Wallet Balance: ₦100,000.00
Status: Available for use
```

### After Request (While Pending Admin Review)
```
Wallet Balance: ₦50,000.00
Status: ₦50,000 in limbo (pending approval)
Available: ₦50,000
Reason: Already debited - user can't re-spend
```

### If Approved
```
Wallet Balance: ₦50,000.00
Status: Being processed via bank
Action: Payment provider processes transfer
```

### If Rejected
```
Wallet Balance: ₦100,000.00
Status: Refunded
Reason: Admin rejected or provider failed
```

---

## 📊 Database Schema

### PayoutRequest Table
```
id          | UUID Primary Key
vendor_id   | FK to Vendor (NULL for customers)
user_id     | FK to CustomUser (NULL for vendors)
amount      | DECIMAL(12,2)
status      | pending|processing|successful|failed|cancelled
bank_name   | VARCHAR(100)
account_number | VARCHAR(20)
account_name | VARCHAR(200)
reference   | VARCHAR(100) UNIQUE - Format: WTH-XXXXXXXXXX
created_at  | DATETIME
processed_at | DATETIME nullable
failure_reason | TEXT
```

### PaymentPIN Table
```
user_id     | OneToOne FK to CustomUser
pin_hash    | VARCHAR(255) - Hashed with make_password()
is_default  | BOOLEAN - True if still using 0000
created_at  | DATETIME
updated_at  | DATETIME
```

---

## 🚨 Error Messages & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "PIN not configured" | Never set PIN | User: POST /set-payment-pin/ |
| "Please set secure PIN" | Using default (0000) | User: POST /set-payment-pin/ with new PIN |
| "Invalid PIN" | Wrong PIN | Retry with correct PIN |
| "Insufficient balance" | ₦X > balance | Wait for more earnings |
| "Bank details required" | Missing bank info (customer) | Customer: Provide all 3 bank fields |
| "Cannot approve/reject" | Wrong status | Withdrawal already processed |

---

## 🔔 Notification System

### When is admin notified?
✅ When vendor/customer submits withdrawal request

### What info is included?
- Requestor name (vendor store name or customer name)
- Requestor email
- Amount (in ₦)
- Bank details
- Unique reference (WTH-XXXXX)
- Request timestamp
- Admin action link

### Notification Channels
📧 **Email:** Full details
🔔 **WebSocket:** Real-time in-app alert
⭐ **Priority:** High for amounts > ₦100,000

---

## 💡 Common Scenarios

### Scenario 1: Vendor Wants to Withdraw

```
1. Vendor visits /wallet/withdraw
2. Vendor enters amount & PIN
3. Request sent to POST /vendor/wallet/request-withdrawal/
4. System checks: PIN ✓, Balance ✓, Bank Details ✓
5. Withdrawal created, wallet debited
6. Admins notified via email & in-app notification
7. Admin reviews in /admin/withdrawals/
8. Admin clicks "Approve"
9. Status → "processing"
10. Vendor notified: "Approved - being processed"
11. Payment provider transfers funds (via Paystack)
12. Status → "successful"
13. Vendor receives confirmation email
```

### Scenario 2: Customer Requests Withdrawal But Gets Rejected

```
1. Customer submits withdrawal with bank details
2. System validates all requirements
3. Request created, wallet debited
4. Admin notified
5. Admin reviews details
6. Admin sees account number doesn't match KYC
7. Admin clicks "Reject"
8. Reason: "Account number doesn't match KYC"
9. Status → "failed"
10. ₦X amount refunded to wallet
11. Customer notified with rejection reason
12. Customer wallet balance restored
13. Customer can retry with correct details
```

### Scenario 3: Insufficient Balance Scenario

```
1. Vendor tries to withdraw ₦50,000
2. Wallet balance only ₦30,000
3. System returns error: "Insufficient balance"
4. Request rejected before DB operation
5. No withdrawal created
6. Wallet unchanged
7. Vendor needs to wait for more orders
```

---

## 🧪 Testing Checklist

Before deploying to production:

- [ ] Vendor can withdraw with sufficient balance & valid PIN
- [ ] Customer rejected if insufficient balance
- [ ] Admin notified when withdrawal requested
- [ ] Admin can approve withdrawal
- [ ] Admin can reject withdrawal with reason
- [ ] Rejected withdrawal refunds wallet
- [ ] Wallet balance never goes negative
- [ ] PIN validation works (correct/incorrect)
- [ ] Default PIN (0000) cannot be used
- [ ] Reference numbers are unique
- [ ] Wallet transactions logged correctly
- [ ] Email notifications sent to admins
- [ ] WebSocket notifications work
- [ ] Admin endpoints require authentication
- [ ] Customer/vendor can't access admin endpoints

---

## 🚀 Deployment Checklist

- [ ] PayoutService imports all correctly
- [ ] NotificationService is configured
- [ ] Email backend configured
- [ ] WebSocket channels layer configured
- [ ] Database migrations run (`manage.py migrate`)
- [ ] BusinessAdmin users created for team
- [ ] Admin email addresses configured
- [ ] Test withdrawal in staging environment
- [ ] Monitor logs for errors
- [ ] Prepare payment provider credentials (Paystack)

---

## 📞 Support & Troubleshooting

### Withdrawal stuck in "processing"
- Check payment provider status
- Verify bank account is valid
- Check logs for provider errors
- Admin can reject and retry

### User forgot PIN
- User clicks forgot PIN link
- Email reset link sent (if implemented)
- Or contact support for admin reset

### Multiple withdrawals by same user
- System allows (but can be limited)
- Each gets unique reference
- Admin can review/approve all

### High-value withdrawal alerts
- Amounts > ₦100,000 marked as "high priority"
- Notification priority: "high" instead of "normal"
- Admin sees these first in dashboard

---

## 🔗 Related Documentation

- **Wallet System**: See `WALLET_DOCUMENTATION.md`
- **Notification System**: See `NOTIFICATION_DOCUMENTATION.md`
- **API Reference**: See `API_DOCUMENTATION.md`
- **Admin Panel**: See `ADMIN_PANEL.md`

---

## Version History

- **v1.0** (Feb 2025)
  - Initial implementation with PIN validation
  - Admin approval workflow
  - Email + WebSocket notifications
  - Wallet refund on rejection
  - Transaction safety guarantees
  - Complete audit trail

---

## Key Files Modified/Created

| File | Changes |
|------|---------|
| `users/services/payout_service.py` | Enhanced with withdrawal methods |
| `users/views.py` | Added/improved withdrawal endpoints |
| `users/models.py` | PayoutRequest & PaymentPIN models |
| `users/serializers.py` | Withdrawal request/response serializers |
| `users/tests/test_withdrawal_flow.py` | Comprehensive test suite |
| `WITHDRAWAL_FLOW_DOCUMENTATION.md` | Full technical documentation |

---

**Last Updated:** February 2, 2025
**Status:** Production Ready ✅
