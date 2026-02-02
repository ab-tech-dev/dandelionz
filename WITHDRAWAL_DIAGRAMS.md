# Withdrawal Flow - Visual Diagrams & Architecture

## 1. Complete Withdrawal Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INITIATES WITHDRAWAL                   │
│                                                                  │
│  POST /vendor/wallet/request-withdrawal/                        │
│  {                                                              │
│    "amount": 50000.00,                                          │
│    "pin": "1234"                                               │
│  }                                                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              STEP 1: INPUT VALIDATION                           │
│                                                                  │
│  ✓ Deserialize request data                                    │
│  ✓ Check amount is decimal                                     │
│  ✓ Check PIN is 4 digits                                       │
│  ✓ No obvious injection attempts                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                   YES           NO
                    │             │
                    ▼             ▼
            Continue      Return Error 400
                          │
                          └─→ "Invalid PIN format"
                              "Amount must be decimal"
                              
                              ▼
                    ┌──────────────────────┐
                    │   RETURN TO USER     │
                    └──────────────────────┘
                    
┌─────────────────────────────────────────────────────────────────┐
│              STEP 2: PIN VERIFICATION                           │
│                                                                  │
│  Call: PayoutService.verify_pin(user, pin)                    │
│                                                                  │
│  ✓ Get PaymentPIN from database                               │
│  ✓ Use Django's check_password() for verification             │
│  ✓ Compare against stored hash                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                 Valid         Invalid
                    │             │
                    ▼             ▼
            Continue      Return Error 400
                          │
                          └─→ "Invalid PIN"
                              
                              ▼
                    ┌──────────────────────┐
                    │   RETURN TO USER     │
                    └──────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              STEP 3: BALANCE VALIDATION                         │
│                                                                  │
│  Call: PayoutService.validate_withdrawal_request()            │
│                                                                  │
│  ✓ Get user's wallet                                           │
│  ✓ Check wallet.balance >= amount                             │
│  ✓ Check amount > 0                                            │
│  ✓ Check PIN not default (0000)                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                 Valid         Invalid
                    │             │
                    ▼             ▼
            Continue      Return Error 400
                          │
                          └─→ "Insufficient balance"
                              "PIN not configured"
                              "PIN is default (0000)"
                              
                              ▼
                    ┌──────────────────────┐
                    │   RETURN TO USER     │
                    └──────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│           STEP 4: CREATE WITHDRAWAL REQUEST                    │
│                    (TRANSACTION SAFE)                          │
│                                                                  │
│  @transaction.atomic                                            │
│  PayoutService.create_withdrawal_request(...)                 │
│                                                                  │
│  BEGIN TRANSACTION                                              │
│  ├─ Create PayoutRequest                                       │
│  │  ├─ status: 'pending'                                       │
│  │  ├─ reference: 'WTH-ABC123DEF456'                          │
│  │  ├─ created_at: now()                                       │
│  │  └─ Save to database                                        │
│  │                                                               │
│  ├─ Debit Wallet                                               │
│  │  ├─ wallet.balance -= amount                               │
│  │  ├─ Create WalletTransaction (DEBIT)                       │
│  │  └─ Save to database                                        │
│  │                                                               │
│  ├─ Notify Admins                                              │
│  │  ├─ Get all BusinessAdmin users                            │
│  │  ├─ For each admin:                                         │
│  │  │  ├─ Create Notification                                  │
│  │  │  ├─ Send WebSocket message                              │
│  │  │  └─ Queue email (async)                                 │
│  │  └─ Log notification sent                                  │
│  │                                                               │
│  └─ Log Transaction                                            │
│     └─ Log: "Withdrawal created: {ref} {amount}"             │
│                                                                  │
│  COMMIT TRANSACTION (all or nothing)                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                 Success        Failed
                    │             │
                    ▼             ▼
            Return 200 OK   Rollback All
            {               Changes
              "success": true
              "reference": "WTH-..."
              "message": "Withdrawal..."
            }
            
                          │
                          ▼
                    Wallet unchanged
                    Notification not sent
                    PayoutRequest not created
                    Return Error 400

┌─────────────────────────────────────────────────────────────────┐
│           STEP 5: ADMIN NOTIFICATION SENT                      │
│                                                                  │
│  Each Admin Receives:                                           │
│                                                                  │
│  Email:                          WebSocket:                     │
│  ├─ Subject: "{Name} Withdrawal │ ├─ Title                     │
│  │   Request - ₦{amount}"        │ ├─ Message                  │
│  ├─ Amount: ₦{amount}            │ ├─ Priority: high/normal    │
│  ├─ Account: {account_number}   │ ├─ Action URL               │
│  ├─ Reference: {ref}             │ └─ Metadata                 │
│  ├─ Action: Review Withdrawal    │                             │
│  └─ Timestamp                    │ In-App:                     │
│                                  │ ├─ Notification center      │
│                                  │ ├─ Badge count ++           │
│                                  │ └─ Can click to approve     │
│                                                                  │
│  Admin sees notification:                                       │
│  ✓ Can list pending withdrawals                               │
│  ✓ Can view withdrawal details                                │
│  ✓ Can approve or reject                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    ADMIN TAKES        ADMIN TAKES       ADMIN IGNORES
    ACTION: APPROVE    ACTION: REJECT    (Waiting)
        │                  │                  │
        │                  │                  │
        ▼                  ▼                  ▼
        
┌──────────────────────────────────────┐ ┌────────────────────────────────┐
│      APPROVED WORKFLOW               │ │    REJECTED WORKFLOW           │
│                                      │ │                                │
│  POST /admin/approve-withdrawal/    │ │ POST /admin/reject-withdrawal/ │
│  {                                   │ │ {                              │
│    "withdrawal_id": "uuid",         │ │   "withdrawal_id": "uuid",    │
│    "notes": "Approved"              │ │   "reason": "Account mismatch" │
│  }                                   │ │ }                              │
│                                      │ │                                │
│  UPDATE PayoutRequest                │ │ UPDATE PayoutRequest           │
│  ├─ status: 'processing'             │ │ ├─ status: 'failed'            │
│  ├─ processed_at: now()              │ │ ├─ processed_at: now()         │
│  └─ Save                             │ │ ├─ failure_reason: "..."       │
│                                      │ │ └─ Save                        │
│  NOTIFY USER                         │ │                                │
│  ├─ Title: "Approved"                │ │ REFUND WALLET                  │
│  ├─ Message: "Being processed"       │ │ ├─ wallet.balance += amount   │
│  └─ Email sent                       │ │ ├─ Create WalletTransaction   │
│                                      │ │ │  (CREDIT)                    │
│  NEXT: Payment provider              │ │ ├─ Save                        │
│  ├─ Call Paystack/Flutterwave       │ │ │                              │
│  ├─ Transfer funds                   │ │ NOTIFY USER                    │
│  ├─ Get confirmation                 │ │ ├─ Title: "Rejected"           │
│  └─ Mark successful                  │ │ ├─ Message: "Reason given"     │
│                                      │ │ ├─ Show refunded amount        │
│  UPDATE PayoutRequest                │ │ └─ Email sent                  │
│  ├─ status: 'successful'             │ │                                │
│  └─ Save                             │ │ User sees notification:        │
│                                      │ │ ✓ Amount back in wallet       │
│  User sees notification:             │ │ ✓ Knows why rejected          │
│  ✓ Withdrawal approved               │ │ ✓ Can try again               │
│  ✓ Being transferred                 │ │                                │
│  ✓ Reference number                  │ │ Withdrawal closed             │
│                                      │ │                                │
│  Withdrawal complete                 │ │                                │
└──────────────────────────────────────┘ └────────────────────────────────┘
```

---

## 2. Database State Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WITHDRAWAL STATE MACHINE                         │
└─────────────────────────────────────────────────────────────────────┘

                    ┌─────────────┐
                    │   CREATED   │
                    │  (Pending)  │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
        APPROVED      REJECTED       CANCELLED
        (Processing)  (Failed)       (Cancelled)
            │              │              │
            └──────────────┼──────────────┘
                           │
                    ┌──────▼──────┐
                    │ SUCCESSFUL  │
                    │ (Complete)  │
                    └─────────────┘

State Transitions:
pending    ──approval──>  processing  ──success──>  successful
pending    ──rejection─>  failed
pending    ──timeout──>   cancelled

Database Record:
pending     → created_at: set,  processed_at: NULL,  failure_reason: NULL
processing  → processed_at: set, failure_reason: NULL
successful  → processed_at: set, failure_reason: NULL
failed      → processed_at: set, failure_reason: "..."
```

---

## 3. Wallet State During Withdrawal

```
User Wallet: Starting Balance ₦100,000

Step 1: Request Withdrawal (₦50,000)
┌────────────────────────────────┐
│ Wallet State                   │
├────────────────────────────────┤
│ Total Balance:    ₦100,000     │
│ Pending Debit:    ₦50,000      │
│ Available:        ₦50,000      │
│ Status: Locked    (Can't spend)│
└────────────────────────────────┘

Step 2: Debit Executed (Atomic)
┌────────────────────────────────┐
│ Wallet State                   │
├────────────────────────────────┤
│ Total Balance:    ₦50,000      │ ← Reduced!
│ Pending Debit:    ₦0           │
│ Available:        ₦50,000      │
│ Status: In Review              │
└────────────────────────────────┘

Step 3a: Approved Path (Success)
┌────────────────────────────────┐
│ Wallet State                   │
├────────────────────────────────┤
│ Total Balance:    ₦50,000      │
│ In Processing:    ₦50,000      │
│ Available:        ₦0           │ ← Can't use yet
│ Status: Processing             │
│                                │
│ (Funds transferred by bank)    │
│                                │
│ Final: ₦50,000 gone            │
└────────────────────────────────┘

Step 3b: Rejected Path (Refund)
┌────────────────────────────────┐
│ Wallet State                   │
├────────────────────────────────┤
│ Total Balance:    ₦50,000      │
│ Refunded:         ₦50,000      │
│ Available:        ₦100,000     │ ← Back to original!
│ Status: Available              │
│                                │
│ (Full amount credited back)    │
└────────────────────────────────┘
```

---

## 4. API Call Flow Sequence

```
User                API View            PayoutService        Database
 │                    │                     │                   │
 │─Withdrawal Request→│                     │                   │
 │                    │                     │                   │
 │                    │─Deserialize Input─→│                   │
 │                    │←Return: OK          │                   │
 │                    │                     │                   │
 │                    │─verify_pin()───────→│                   │
 │                    │←PIN OK              │                   │
 │                    │                     │                   │
 │                    │─validate_request()→│                   │
 │                    │←Validation OK       │                   │
 │                    │                     │                   │
 │                    │─create_withdrawal()│                   │
 │                    │                     │─BEGIN TRANSACTION→│
 │                    │                     │                   │
 │                    │                     │─Create Payout───→│
 │                    │                     │←PayoutRequest OK  │
 │                    │                     │                   │
 │                    │                     │─Debit Wallet────→│
 │                    │                     │←Wallet OK         │
 │                    │                     │                   │
 │                    │                     │─Create TxnLog───→│
 │                    │                     │←TxnLog OK         │
 │                    │                     │                   │
 │                    │                     │─notify_admins()  │
 │                    │                     │  ├─Get Admins────→│
 │                    │                     │  │←Admin List OK  │
 │                    │                     │  │                │
 │                    │                     │  ├─Create Notif─→│
 │                    │                     │  │←Notification OK│
 │                    │                     │  │                │
 │                    │                     │  └─Send Email    │
 │                    │                     │    (async task)  │
 │                    │                     │                   │
 │                    │                     │─COMMIT TRANS.───→│
 │                    │                     │←OK                │
 │                    │                     │                   │
 │←HTTP 200 JSON────←│                     │                   │
 │{success: true}    │                     │                   │
 │                   │                     │                   │

Admin              AdminView           PayoutService         Database
 │                   │                    │                    │
 │─List Withdrawals→│                    │                    │
 │                   │─Query────────────────────────────────→│
 │                   │←Withdrawals←────────────────────────── │
 │←List Response────│                    │                    │
 │                   │                    │                    │
 │─Approve Request──│                    │                    │
 │ {withdrawal_id}  │                    │                    │
 │                   │─update_status()──→│                    │
 │                   │                    │─BEGIN TRANS.─────→│
 │                   │                    │                   │
 │                   │                    │─Update Record───→│
 │                   │                    │←OK                │
 │                   │                    │                   │
 │                   │                    │─notify_user()    │
 │                   │                    │ (WebSocket/Email)│
 │                   │                    │                   │
 │                   │                    │─COMMIT───────────→│
 │                   │                    │←OK                │
 │                   │                    │                   │
 │←HTTP 200 JSON────│                    │                   │
 │{success: true}   │                    │                   │
```

---

## 5. Authentication & Authorization Flow

```
┌────────────────┐
│  User Request  │
│ (with token)   │
└────────┬───────┘
         │
         ▼
┌────────────────────────────────┐
│  Token Validation              │
│  ├─ Check Bearer token         │
│  ├─ Verify signature           │
│  ├─ Check expiration           │
│  └─ Get User from token        │
└────────┬───────────────────────┘
         │
    ┌────┴────┐
    │          │
  Valid      Invalid
    │          │
    ▼          ▼
Continue    401 Unauthorized
    │          │
    ▼          ▼
┌─────────────────────────────────┐
│  Check User Type                │
│  ├─ Is Vendor?                  │
│  │  ├─ vendor_profile exists    │
│  │  └─ vendor_profile.status OK │
│  │                               │
│  └─ Is Customer?                │
│     └─ customer_profile exists  │
└────────┬────────────────────────┘
         │
    ┌────┴─────────┐
    │              │
  Valid         Invalid
    │              │
    ▼              ▼
Continue       403 Forbidden
    │
    ▼
┌──────────────────────────────────┐
│  Check Additional Permissions    │
│  ├─ For Vendors:                 │
│  │  └─ Vendor not suspended      │
│  │                               │
│  ├─ For Admins:                  │
│  │  ├─ BusinessAdmin exists      │
│  │  ├─ can_manage_payouts = True │
│  │  └─ User not suspended        │
│  │                               │
│  └─ For Customers:               │
│     └─ Customer not suspended    │
└────────┬───────────────────────┘
         │
    ┌────┴─────┐
    │           │
  OK      Denied
    │           │
    ▼           ▼
Execute     403 Forbidden
 Request
```

---

## 6. Error Handling Flowchart

```
                    Withdrawal Request
                          │
                          ▼
            ┌─────────────────────────┐
            │  Exception Caught?      │
            └────────┬────────────────┘
                     │
              ┌──────┴──────┐
              │             │
             YES           NO
              │             │
              ▼             ▼
         Handle Error   Continue
              │             │
              ▼             ▼
      ┌────────────────┐   │
      │ Error Type?    │   │
      └────┬───────────┘   │
           │               │
    ┌──────┼───────┐       │
    │      │       │       │
    ▼      ▼       ▼       │
  Debit  Balance  PIN   │
  Error  Error    Error │
    │      │       │      │
    └──────┴───────┴──────┤
                   │      │
         ┌─────────┴───────┘
         │
         ▼
    ┌──────────────────┐
    │ Log Error        │
    ├──────────────────┤
    │ Level: ERROR     │
    │ Include: stacktrace
    │ Include: context │
    └─────────┬────────┘
              │
              ▼
      ┌───────────────────┐
      │ Return HTTP Error │
      ├───────────────────┤
      │ 400: Bad Request  │
      │ 403: Forbidden    │
      │ 404: Not Found    │
      │ 500: Server Error │
      └─────────┬─────────┘
                │
                ▼
          ┌──────────────┐
          │ User Sees    │
          │ Error Message│
          └──────────────┘

Error Messages Returned:
─────────────────────────
"Invalid PIN"
"PIN not configured"
"PIN is default (0000)"
"Insufficient balance"
"Amount must be > 0"
"Bank details required"
"Withdrawal not found"
"Cannot approve/reject"
```

---

## 7. Notification System Architecture

```
                  PayoutService
               notify_admins()
                      │
         ┌────────────┼────────────┐
         │            │            │
         ▼            ▼            ▼
    Get Admins   Loop Each      Build Msg
                  Admin
         │            │            │
         └────────────┼────────────┘
                      │
                      ▼
         NotificationService
           create_notification()
                      │
         ┌────────────┼────────────┐
         │            │            │
    Create DB   Prepare       Send
    Record      Channels      Async
         │            │            │
         ▼            ▼            ▼
    Notification  WebSocket    Celery Task
    Object        Send         │
         │            │        │
         └────────────┼────────┤
                      │        │
         ┌────────────┴────────┘
         │
         ▼
    Admin Receives:
    ├─ In-app notification
    │  └─ Shows in notification center
    ├─ WebSocket notification
    │  └─ Real-time if online
    ├─ Email notification
    │  └─ Sent asynchronously
    └─ Configurable by priority
```

---

**Last Updated:** February 2, 2025  
**Version:** 1.0
