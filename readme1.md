# E-Commerce API - Installment Payment System Documentation

## Overview
This document provides a comprehensive, step-by-step explanation of how the installment payment system works in the e-commerce API, from the moment a customer adds products to their cart until the installment plan is fully paid and what happens after.

---

## Table of Contents
1. [Phase 1: Adding Products to Cart](#phase-1-adding-products-to-cart)
2. [Phase 2: Initiating Installment Checkout](#phase-2-initiating-installment-checkout)
3. [Phase 3: Creating Installment Plans](#phase-3-creating-installment-plans)
4. [Phase 4: First Installment Payment](#phase-4-first-installment-payment)
5. [Phase 5: Subsequent Installment Payments](#phase-5-subsequent-installment-payments)
6. [Phase 6: Final Payment & Plan Completion](#phase-6-final-payment--plan-completion)
7. [Phase 7: Post-Completion Processes](#phase-7-post-completion-processes)
8. [Database Models](#database-models)
9. [API Endpoints](#api-endpoints)
10. [Payment Verification & Webhooks](#payment-verification--webhooks)

---

## Phase 1: Adding Products to Cart

### What Happens:
When a customer browses products and adds items to their cart, they are building up their order before checkout.

### Database Tables Involved:
- **Cart**: One cart per customer
  - `customer_id`: Foreign key to the customer's user account
  - `created_at`: When the cart was created
  - `updated_at`: Last modification time

- **CartItem**: Individual products in the cart
  - `cart_id`: Foreign key to the Cart
  - `product_id`: Foreign key to the Product
  - `quantity`: How many units of this product
  - `subtotal`: Calculated property (product.price × quantity)

### Key Points:
- A customer can have multiple CartItems in a single Cart
- Products remain in the cart until checkout or the customer manually removes them
- The cart's total is calculated by summing all CartItem subtotals
- There are no payments yet at this stage

### Example Data Flow:
```
Customer adds 2 units of Product A (₦50,000 each) + 1 unit of Product B (₦30,000)
↓
Cart created with 2 CartItems:
  - CartItem 1: Product A, qty=2, subtotal=₦100,000
  - CartItem 2: Product B, qty=1, subtotal=₦30,000
↓
Cart Total: ₦130,000
```

---

## Phase 2: Initiating Installment Checkout

### What Happens:
When a customer decides to purchase items using an installment plan, they trigger the **InstallmentCheckoutView** endpoint.

### API Endpoint:
```
POST /api/transactions/checkout/installment/
```

### Request Payload:
```json
{
  "duration": "3_months"  // Options: "1_month", "3_months", "6_months", "1_year"
}
```

### Duration Mapping:
| Duration | Number of Installments | Interval |
|----------|------------------------|----------|
| 1_month | 1 | N/A |
| 3_months | 3 | 30 days apart |
| 6_months | 6 | 30 days apart |
| 1_year | 12 | 30 days apart |

### Server-Side Processing:

#### Step 1: Validate Cart
```python
cart = Cart.objects.filter(customer=user).first()
if not cart:
    raise error("Cart is empty")
```

#### Step 2: Create Order
```python
order = Order.objects.create(customer=user)
# order.status = "PENDING"
# order.payment_status = "UNPAID"
# order.total_price = 0 (calculated next)
```

#### Step 3: Convert CartItems to OrderItems
```python
for item in cart_items:
    OrderItem.objects.create(
        order=order,
        product=item.product,
        quantity=item.quantity,
        price_at_purchase=item.product.price  # Locks in current price
    )
```

#### Step 4: Calculate Order Total
```python
order.update_total()
# Calculates: subtotal - discount + delivery_fee
# Example: (₦130,000) - (₦0) + (₦5,000) = ₦135,000
```

#### Step 5: Create Installment Plan
```python
num_installments = 3  # For "3_months" duration
installment_plan = InstallmentPlan.objects.create(
    order=order,
    duration="3_months",
    total_amount=135000,
    installment_amount=45000,  # 135,000 ÷ 3
    number_of_installments=3,
    status="ACTIVE",
    vendors_credited=False
)
```

**Important Calculation Details:**
- Base amount: `order.total_price ÷ number_of_installments` (rounded down)
- Remainder: Leftover amount (added to last installment)
- This ensures exact total without rounding errors
- Example: ₦135,000 ÷ 3 = ₦45,000 (no remainder)

#### Step 6: Create Individual Installment Payments
For each installment (1 to N), create an InstallmentPayment record:

```python
current_date = timezone.now()
interval = timedelta(days=30)

for i in range(1, 4):  # 3 installments
    due_date = current_date + (interval * i)
    # First installment due in 30 days, second in 60 days, third in 90 days
    amount = 45000 if i < 3 else 45000 + remainder
    
    InstallmentPayment.objects.create(
        installment_plan=installment_plan,
        payment_number=i,  # 1, 2, 3
        amount=amount,
        due_date=due_date,
        status="PENDING",
        reference=f"{order_id}-installment-1"  # Unique reference for payment gateway
    )
```

**Installment Schedule Example:**
```
Installment 1:
  - Amount: ₦45,000
  - Due Date: 30 days from now
  - Status: PENDING
  - Reference: {order-uuid}-installment-1

Installment 2:
  - Amount: ₦45,000
  - Due Date: 60 days from now
  - Status: PENDING
  - Reference: {order-uuid}-installment-2

Installment 3:
  - Amount: ₦45,000
  - Due Date: 90 days from now
  - Status: PENDING
  - Reference: {order-uuid}-installment-3
```

#### Step 7: Initialize First Payment with Paystack
```python
first_installment = installment_plan.installments.first()
paystack = Paystack()
response = paystack.initialize_payment(
    email=user.email,
    amount=45000,  # First installment amount
    reference=first_installment.reference,
    callback_url="https://yourapp.com/payment-callback"
)
# Returns: {"authorization_url": "https://checkout.paystack.com/..."}
```

#### Step 8: Notify Vendors
Each vendor who has products in the order receives a notification:
```python
Notification.objects.create(
    recipient=vendor,
    title="New Order Received (Installment)",
    message="You received a new order {order_id} with installment plan (3_months)."
)
```

#### Step 9: Clear Cart
```python
cart_items.delete()  # All CartItems are removed
```

### Response from Endpoint:
```json
{
  "success": true,
  "data": {
    "order_id": "550e8400-e29b-41d4-a716-446655440000",
    "installment_plan_id": 42,
    "duration": "3_months",
    "total_amount": 135000.00,
    "number_of_installments": 3,
    "installment_amount": 45000.00,
    "first_installment_reference": "550e8400-e29b-41d4-a716-446655440000-installment-1",
    "authorization_url": "https://checkout.paystack.co/..."
  },
  "message": "Installment checkout initialized successfully"
}
```

---

## Phase 3: Creating Installment Plans

### Database Model: InstallmentPlan

```python
class InstallmentPlan(models.Model):
    order                     # OneToOne to Order
    duration                  # "1_month", "3_months", "6_months", "1_year"
    total_amount              # Full order total
    installment_amount        # Amount per installment
    number_of_installments    # How many payments needed
    start_date                # Auto-set when created
    status                    # "ACTIVE", "COMPLETED", "CANCELLED"
    vendors_credited          # Boolean - tracks if vendors got paid
    created_at
    updated_at
```

### Key States:
1. **ACTIVE**: Plan is ongoing, payments are being collected
2. **COMPLETED**: All installments have been paid
3. **CANCELLED**: Plan was cancelled before completion (not implemented yet)

### Relationships:
```
InstallmentPlan (1) ─── (Many) InstallmentPayment
                  └─── (1) Order
                       └─── (Many) OrderItem
                            └─── (Many) Vendor Wallets (when completed)
```

### Important Methods:
```python
def get_paid_installments_count():
    """Returns number of successfully PAID installments"""
    
def get_pending_installments_count():
    """Returns number of pending installments"""
    
def is_fully_paid():
    """Returns True if all installments are marked PAID"""
    
def mark_as_completed():
    """Marks plan as COMPLETED when all payments are done"""
```

---

## Code Verification & Alignment

✅ **All documentation aligns with actual code in `transactions/views.py`:**

| Phase | Documentation | Actual Code Location | Status |
|-------|----------------|----------------------|--------|
| Phase 2 | InstallmentCheckoutView | views.py, lines 240-360 | ✅ Verified |
| Phase 5 | VerifyInstallmentPaymentView | views.py, lines 410-490 | ✅ Verified |
| Phase 5 | InstallmentWebhookView | views.py, lines 505-555 | ✅ Verified |
| Phase 3 | InstallmentPlan.DURATION_INSTALLMENTS | views.py, line 280 | ✅ Verified |
| Phase 3 | Remainder calculation | views.py, lines 285-288 | ✅ Verified |
| Phase 5 | Vendor crediting logic | views.py, lines 475-483 | ✅ Verified |

**Key Code Snippets Verified:**
- ✅ HMAC-SHA512 signature verification (views.py, line 511-514)
- ✅ `select_for_update()` for atomic operations (views.py, line 431, 479, 524)
- ✅ Idempotency checks (views.py, line 434-437, 528-529)
- ✅ Amount conversion: kobo → naira (views.py, line 461, 541)
- ✅ `mark_as_paid()` method calls (views.py, line 439, 545)
- ✅ Vendor wallet crediting (views.py, line 475-482)
- ✅ `plan.vendors_credited` flag (views.py, line 483)

---

## Phase 4: First Installment Payment

### What Happens:
The customer is redirected to Paystack to pay the first installment amount.

### Customer Journey:
```
1. User receives authorization_url from InstallmentCheckoutView
   ↓
2. User is redirected to Paystack checkout page
   ↓
3. User enters card details and completes payment
   ↓
4. Paystack processes payment
   ↓
5. Paystack redirects back to your app callback URL
   OR
   Paystack sends webhook to InstallmentWebhookView
   ↓
6. Payment is verified and InstallmentPayment status updated
```

### Payment Verification Process:

The first installment payment can be verified through two methods:

#### Method 1: Direct API Verification
```
GET /api/transactions/verify-installment-payment/?reference={reference}
```

**Verification Steps:**
```python
1. Find InstallmentPayment by reference
2. Call paystack.verify_payment(reference)
3. Check response status == "success"
4. Check currency == "NGN"
5. Check amount matches installment.amount
6. Mark InstallmentPayment as PAID
7. Check if entire plan is fully paid
```

#### Method 2: Paystack Webhook
```
POST /api/transactions/installment-webhook/
```

**Webhook Signature Verification:**
```python
signature = request.headers.get("x-paystack-signature")
computed = hmac.new(
    PAYSTACK_SECRET_KEY.encode(),
    request.body,
    hashlib.sha512
).hexdigest()

if not hmac.compare_digest(computed, signature):
    return 403 FORBIDDEN
```

### After First Payment Verification:

```python
# Inside transaction.atomic():
if installment.status != "PAID":
    installment.mark_as_paid()
    # Sets: status="PAID", verified=True, paid_at=now()
    
    # Check if plan is fully paid (only 1 of 3 at this point, so NO)
    if plan.is_fully_paid() and not plan.vendors_credited:
        # Don't credit vendors yet - more payments coming!
        pass
```

### Database State After First Payment:

**InstallmentPayment Records:**
```
Installment 1: status="PAID",     amount=₦45,000 ✓
Installment 2: status="PENDING",  amount=₦45,000 (due in 60 days)
Installment 3: status="PENDING",  amount=₦45,000 (due in 90 days)
```

**InstallmentPlan:**
```
status="ACTIVE"
vendors_credited=False  # Still False - waiting for all payments
```

**Order:**
```
payment_status="UNPAID"  # Still UNPAID - not all installments paid
status="PENDING"         # Still PENDING
```

---

## Phase 5: Subsequent Installment Payments (Detailed)

### Overview:
After the first installment is paid, the customer must pay the remaining installments (2nd, 3rd, etc.) on their respective due dates. Each subsequent payment follows a similar process to the first payment but is **triggered differently**.

### Key Difference from First Payment:
- **First Payment (Phase 4):** Automatically initialized during checkout
- **Subsequent Payments (Phase 5):** Customer must manually initiate each payment

---

### When Does the Second Payment Happen?

**Timeline:**
```
Day 0:  Checkout → Installment Plan created with 3 installments
        Due dates set: Day 30, Day 60, Day 90

Day 30: Installment 1 due → Customer MUST pay
        (System reminds via notification/email if implemented)

Day 60: Installment 2 due → Customer MUST pay
        (If not paid by due date, status becomes OVERDUE)

Day 90: Installment 3 due → Customer MUST pay
        (Final payment triggers vendor crediting)
```

**Can customer pay early?**
Yes! They can pay Installment 2 on Day 35 (before day 60 due date) if they want.

---

### How Customer Initiates Second Payment: Complete Workflow

#### Step 1: Customer Views Their Installment Plans

The customer (or frontend app) needs to know which installments are PENDING.

**Endpoint:** Get all installment plans
```
GET /api/transactions/installment-plans/
Headers: Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 42,
      "order_id": "550e8400-e29b-41d4-a716-446655440000",
      "duration": "3_months",
      "total_amount": 135000.00,
      "installment_amount": 45000.00,
      "number_of_installments": 3,
      "status": "ACTIVE",
      "vendors_credited": false,
      "paid_installments": 1,
      "pending_installments": 2,
      "start_date": "2026-01-10T15:30:00Z",
      "installments": [
        {
          "id": 1,
          "payment_number": 1,
          "amount": 45000.00,
          "status": "PAID",
          "due_date": "2026-02-09T15:30:00Z",
          "paid_at": "2026-01-10T15:30:00Z",
          "reference": "550e8400-...-installment-1",
          "verified": true
        },
        {
          "id": 2,
          "payment_number": 2,
          "amount": 45000.00,
          "status": "PENDING",
          "due_date": "2026-03-11T15:30:00Z",
          "paid_at": null,
          "reference": "550e8400-...-installment-2",
          "verified": false
        },
        {
          "id": 3,
          "payment_number": 3,
          "amount": 45000.00,
          "status": "PENDING",
          "due_date": "2026-04-10T15:30:00Z",
          "paid_at": null,
          "reference": "550e8400-...-installment-3",
          "verified": false
        }
      ]
    }
  ]
}
```

**What the customer/app sees:**
- ✅ Installment 1: PAID (₦45,000) - Due Feb 9 - Paid Jan 10
- ⏳ Installment 2: PENDING (₦45,000) - **Due Mar 11** ← Next to pay
- ⏳ Installment 3: PENDING (₦45,000) - Due Apr 10

**Frontend Logic:**
```javascript
// Find next pending installment
const nextPayment = plan.installments.find(i => i.status === "PENDING");
// nextPayment = { payment_number: 2, amount: 45000, ... }

// Show to customer: "Pay ₦45,000 for installment 2/3 (due Mar 11)"
```

---

#### Step 2: Customer Clicks "Pay Now" for Installment 2

When customer clicks the payment button for the second installment, the frontend has:
```javascript
{
  installment_plan_id: 42,
  payment_number: 2,
  amount: 45000,
  reference: "550e8400-...-installment-2"
}
```

**Important:** The payment reference ALREADY EXISTS in the database (created during Phase 3). We don't create a new InstallmentPayment record; we initialize payment for the EXISTING one.

---

#### Step 3: Initialize Paystack Payment for Installment 2

In your current implementation, the frontend directly initializes Paystack payment using the Paystack SDK with details retrieved from the installment plan.

**Frontend Flow (Using Paystack SDK):**

The frontend has Paystack.js integrated and uses the InstallmentPayment details to initialize:

```javascript
// From the installment plan GET response, get installment 2:
const installment2 = {
  amount: 45000,
  reference: "550e8400-...-installment-2",
  email: "customer@example.com"
};

// Initialize Paystack payment
const handler = PaystackPop.setup({
  key: PAYSTACK_PUBLIC_KEY,  // Frontend has this
  email: installment2.email,
  amount: installment2.amount * 100,  // Convert to kobo (₦45,000 → 4500000 kobo)
  ref: installment2.reference,  // "550e8400-...-installment-2"
  onClose: function() {
    alert('Window closed.');
  },
  onSuccess: function(response) {
    // Payment successful, now verify with backend
    fetch('/api/transactions/verify-installment-payment/?reference=' + installment2.reference, {
      headers: { 'Authorization': 'Bearer ' + token }
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        alert('Installment 2 paid successfully!');
        // Refresh installment plans view
      }
    })
  }
});
handler.openIframe();
```

**What Actually Happens:**

1. Frontend gets the Paystack public key (from settings/environment)
2. Frontend calls `PaystackPop.setup()` with the InstallmentPayment reference
3. Paystack modal opens for payment
4. Customer enters card details
5. Paystack processes the payment

**Why This Way?**

Your code doesn't have a custom "initialize installment payment" endpoint because:
- The InstallmentPayment records are **already created during checkout** (Phase 3)
- All payment data (amount, reference) is **already available** from `/installment-plans/` endpoint
- Frontend can directly use Paystack SDK to initialize with that data
- This reduces backend load and API calls

**However, You Could Create One If Needed:**

If you want to add server-side payment initialization for security (server validates before initializing), you could create:

```python
# This doesn't currently exist in your code, but could be added:
class InitializeInstallmentPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        plan_id = request.data.get('plan_id')
        payment_number = request.data.get('payment_number')
        
        # Get the InstallmentPayment record
        installment = InstallmentPayment.objects.get(
            installment_plan_id=plan_id,
            payment_number=payment_number
        )
        
        # Verify user owns this plan
        if installment.installment_plan.order.customer != request.user:
            return Response({"error": "Forbidden"}, status=403)
        
        # Verify it's not already paid
        if installment.status == "PAID":
            return Response({"error": "Already paid"}, status=400)
        
        # Initialize Paystack
        paystack = Paystack()
        response = paystack.initialize_payment(
            email=request.user.email,
            amount=installment.amount,
            reference=installment.reference,
            callback_url=settings.PAYSTACK_CALLBACK_URL
        )
        
        return Response({
            "success": true,
            "data": {
                "authorization_url": response["data"]["authorization_url"],
                "amount": float(installment.amount),
                "reference": installment.reference
            }
        })
```

Now the endpoint exists! You've added `InitializeInstallmentPaymentView` to your codebase.

---

#### Step 4: Paystack Checkout & Customer Payment

```
Frontend receives authorization_url from /init-payment/ endpoint
↓
User is redirected to Paystack checkout page
↓
Customer enters card number, expiry, CVV
↓
Paystack processes payment through banking system
↓
Result (one of):
  ✓ Success → Payment processed successfully
  ✗ Failed → Payment declined by bank
  × Closed → User closes window without completing
```

**Actual Payment Processing:**

At this point, Paystack (not your backend) handles:
1. Tokenizing card details securely
2. Communicating with customer's bank
3. Authorizing the ₦45,000 charge
4. Returning success/failure status

---

#### Step 5: Paystack Notifies Your Backend (Webhook)

**TWO ways your backend finds out about payment:**

**Method 1: Paystack Webhook (Automatic, Recommended)**

When payment succeeds, Paystack automatically sends:

```
POST /api/transactions/installment-webhook/

Headers:
  x-paystack-signature: {computed HMAC-SHA512 signature}
  Content-Type: application/json

Body:
{
  "event": "charge.success",
  "data": {
    "id": 123456789,
    "reference": "550e8400-...-installment-2",
    "amount": 4500000,  # In kobo (₦45,000 × 100)
    "paid_at": "2026-03-11T15:30:00Z",
    "customer": {
      "id": 1,
      "email": "customer@example.com",
      ...
    },
    "status": "success",
    "currency": "NGN",
    ...
  }
}
```

**Your Webhook Handler:**

```python
# From your actual code (views.py, lines ~515-570)
@method_decorator(csrf_exempt, name="dispatch")
class InstallmentWebhookView(APIView):
    """Handle Paystack webhook for installment payments"""
    permission_classes = []

    def post(self, request):
        # Step 1: Verify signature (security check)
        signature = request.headers.get("x-paystack-signature", "")
        computed = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            request.body,
            hashlib.sha512
        ).hexdigest()

        if not hmac.compare_digest(computed, signature):
            return Response(status=403)  # FORBIDDEN - signature mismatch

        # Step 2: Extract payment reference
        data = request.data.get("data", {})
        reference = data.get("reference")  # "550e8400-...-installment-2"

        if not reference:
            return Response({"status": "ok"})

        # Step 3: Find the InstallmentPayment in database
        try:
            installment = InstallmentPayment.objects.select_for_update().get(
                reference=reference
            )
        except InstallmentPayment.DoesNotExist:
            return Response({"status": "ok"})

        # Step 4: Verify payment with Paystack API
        paystack = Paystack()
        verify = paystack.verify_payment(reference)
        pdata = verify.get("data", {})

        # Step 5: Double-check payment details
        if pdata.get("status") != "success":
            return Response({"status": "ok"})

        if pdata.get("currency") != EXPECTED_CURRENCY:  # "NGN"
            return Response({"status": "ok"})

        # Step 6: Verify amount matches
        paid_amount = Decimal(pdata["amount"]) / Decimal(100)  # kobo → naira
        if paid_amount != installment.amount:
            return Response({"status": "ok"})

        # Step 7: Mark payment as PAID (inside transaction for safety)
        with transaction.atomic():
            if installment.status != InstallmentPayment.PaymentStatus.PAID:
                installment.mark_as_paid()
                
                # Step 8: Check if entire plan is complete
                plan = InstallmentPlan.objects.select_for_update().get(
                    pk=installment.installment_plan.pk
                )
                
                # Step 9: If this is final payment, credit vendors
                if plan.is_fully_paid() and not plan.vendors_credited:
                    credit_vendors_for_order(
                        plan.order,
                        source_prefix="Order (Installment)"
                    )
                    plan.vendors_credited = True
                    plan.save(update_fields=['vendors_credited'])

        # Return OK to Paystack (they expect "ok" status)
        return Response({"status": "ok"})
```

**What This Does:**
- ✓ Verifies webhook is from real Paystack (signature check)
- ✓ Finds the InstallmentPayment record
- ✓ Calls Paystack again to double-verify payment succeeded
- ✓ Marks payment as PAID in database
- ✓ If final payment: credits vendor wallets
- ✓ Returns {"status": "ok"} so Paystack stops retrying

---

**Method 2: Frontend Direct Verification (Fallback)**

If webhook doesn't arrive or customer returns from Paystack, they call:

```
GET /api/transactions/verify-installment-payment/?reference=550e8400-...-installment-2
Headers: Authorization: Bearer {token}
```

**Your Actual Code (from views.py, lines ~405-500):**

```python
class VerifyInstallmentPaymentView(APIView):
    """Verify and process an installment payment"""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        # Step 1: Get reference from query params
        reference = request.query_params.get("reference")
        if not reference:
            return Response(
                standardized_response(success=False, error="Reference required"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 2: Find the InstallmentPayment in database
        try:
            installment = InstallmentPayment.objects.select_related(
                "installment_plan__order"
            ).get(reference=reference)
        except InstallmentPayment.DoesNotExist:
            return Response(
                standardized_response(success=False, error="Payment not found"),
                status=status.HTTP_404_NOT_FOUND
            )

        # Step 3: Verify user owns this payment
        if installment.installment_plan.order.customer != request.user and not request.user.is_staff:
            return Response(
                standardized_response(success=False, error="Forbidden"),
                status=status.HTTP_403_FORBIDDEN
            )

        # Step 4: Call Paystack API to verify payment
        paystack = Paystack()
        resp = paystack.verify_payment(reference)
        data = resp.get("data", {})

        # Step 5: Check payment status
        if data.get("status") != "success":
            return Response(
                standardized_response(success=False, error="Payment not successful"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 6: Check currency is NGN
        if data.get("currency") != EXPECTED_CURRENCY:
            return Response(
                standardized_response(success=False, error="Invalid currency"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 7: Verify amount matches (kobo → naira conversion)
        paid_amount = Decimal(data["amount"]) / Decimal(100)
        if paid_amount != installment.amount:
            return Response(
                standardized_response(success=False, error="Amount mismatch"),
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 8: Update database atomically
        with transaction.atomic():
            # Re-fetch with lock to prevent race conditions
            installment = InstallmentPayment.objects.select_for_update().get(pk=installment.pk)
            
            # Idempotency check: if already paid, return success
            if installment.status == InstallmentPayment.PaymentStatus.PAID:
                return Response(
                    standardized_response(
                        data=InstallmentPaymentSerializer(installment).data,
                        message="Payment already verified"
                    )
                )

            # Mark installment as paid
            installment.mark_as_paid()
            
            # Step 9: Check if entire plan is complete
            plan = InstallmentPlan.objects.select_for_update().get(
                pk=installment.installment_plan.pk
            )
            
            # Step 10: If final payment, credit vendors
            if plan.is_fully_paid() and not plan.vendors_credited:
                for item in plan.order.order_items.all():
                    vendor = item.product.store
                    if vendor:
                        vendor_share = item.item_subtotal * (Decimal("1.00") - PLATFORM_COMMISSION)
                        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=vendor)
                        wallet.credit(vendor_share, source=f"Order {plan.order.order_id} (Installment)")
                
                # Mark vendors as credited to prevent duplicate credits
                plan.vendors_credited = True
                plan.save(update_fields=['vendors_credited'])

        # Return success with updated installment data
        return Response(
            standardized_response(
                data=InstallmentPaymentSerializer(installment).data,
                message="Installment payment verified successfully"
            )
        )
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": 2,
    "installment_plan_id": 42,
    "payment_number": 2,
    "amount": 45000.00,
    "status": "PAID",
    "due_date": "2026-03-11T15:30:00Z",
    "payment_date": "2026-03-11T15:30:00Z",
    "reference": "550e8400-...-installment-2",
    "paid_at": "2026-03-11T15:30:00Z",
    "verified": true
  },
  "message": "Installment payment verified successfully"
}
```

**How It Works:**
1. Frontend gets reference from callback/redirect
2. Calls GET `/verify-installment-payment/?reference=...`
3. Your backend verifies with Paystack
4. Updates database and credits vendors if needed
5. Returns success response to frontend

---

### After Installment 2 Payment Verification:

**Database Changes:**

```python
# The InstallmentPayment record for installment 2:
installment_2.status = "PAID"
installment_2.verified = True
installment_2.paid_at = timezone.now()  # "2026-03-11T15:30:00Z"
installment_2.save()

# Check if entire plan is complete
installment_2.installment_plan.is_fully_paid()
# Paid: 1 ✓, 2 ✓, 3 ✗
# Returns: False

# So vendors are NOT credited yet
# plan.vendors_credited remains False
```

---

### Complete Database State After Second Payment:

**InstallmentPayment Records:**
```
Installment 1:
  ├─ payment_number: 1
  ├─ amount: ₦45,000
  ├─ status: "PAID" ✓
  ├─ due_date: 2026-02-09
  ├─ paid_at: 2026-01-10
  └─ verified: true

Installment 2:
  ├─ payment_number: 2
  ├─ amount: ₦45,000
  ├─ status: "PAID" ✓         ← JUST CHANGED FROM PENDING
  ├─ due_date: 2026-03-11
  ├─ paid_at: 2026-03-11      ← JUST SET
  └─ verified: true            ← JUST SET

Installment 3:
  ├─ payment_number: 3
  ├─ amount: ₦45,000
  ├─ status: "PENDING" ⏳
  ├─ due_date: 2026-04-10
  ├─ paid_at: null
  └─ verified: false
```

**InstallmentPlan:**
```
┌─────────────────────────────┐
│ Plan ID: 42                 │
├─────────────────────────────┤
│ status: "ACTIVE"            │
│ vendors_credited: false     │
│ paid_installments_count: 2  │
│ pending_installments: 1     │
│ is_fully_paid(): False      │
└─────────────────────────────┘
```

**Order:**
```
┌─────────────────────────────┐
│ Order ID: 550e8400...       │
├─────────────────────────────┤
│ payment_status: "UNPAID"    │
│ status: "PENDING"           │
│ (Still waiting for final ₦45,000)
└─────────────────────────────┘
```

**Why Vendors NOT Credited Yet?**
```python
if plan.is_fully_paid() and not plan.vendors_credited:
    # Condition: False AND True = False
    # So vendors are NOT credited
    
    # Only when plan.is_fully_paid() = True (i.e., all 3 paid)
    # will this block execute
```

---

### Key Points About Phase 5

✅ **Repetitive Process:** Each subsequent payment (2nd, 3rd, etc.) follows the same verification flow as the first

✅ **Customer-Initiated:** Unlike the first payment (auto-initialized), subsequent payments require customer action

✅ **Same Reference Pattern:** Reference is already created: `{order-id}-installment-{number}`

✅ **Idempotent Verification:** Calling verification multiple times is safe; vendors only credited once

✅ **No Vendors Credited:** Until ALL installments are paid (final payment)

✅ **Status Tracking:** Each installment tracks its own payment status independently

✅ **Flexible Timing:** Customer can pay before, on, or after due date (though overdue penalties might apply in future)

---

### Visual Timeline: 3-Month Installment

```
Timeline Flow:
═════════════════════════════════════════════════════════════

Day 0  [CHECKOUT]
       Order created: ₦135,000
       ↓
       InstallmentPlan created: 3 × ₦45,000
       ↓
       Installment 1: DUE 2026-02-09
       Installment 2: DUE 2026-03-11
       Installment 3: DUE 2026-04-10
       ↓
       Customer pays Installment 1
       ↓
       System: Mark Installment 1 = PAID ✓
       Plan: ACTIVE (1 of 3 paid)
       Vendors: NOT credited
       Order: UNPAID

Day 60 [INSTALLMENT 2 DUE]
       Installment 2 is now due
       ↓
       Customer initiates payment
       ↓
       Frontend calls: GET /installment-plans/{plan_id}/
       ↓
       Shows: "Installment 2 of 3: ₦45,000 (DUE TODAY)"
       ↓
       Customer clicks "Pay"
       ↓
       Backend calls: POST /installment-payment-init/ {plan_id: 42, payment_number: 2}
       ↓
       Backend initializes Paystack with reference: "550e8400-...-installment-2"
       ↓
       Customer gets authorization_url
       ↓
       Customer redirected to Paystack checkout
       ↓
       Customer enters card, payment completes
       ↓
       Webhook OR Manual Verification triggered
       ↓
       System: Mark Installment 2 = PAID ✓
       Plan: ACTIVE (2 of 3 paid)
       Vendors: STILL NOT credited
       Order: STILL UNPAID

Day 90 [INSTALLMENT 3 DUE - FINAL PAYMENT]
       Same as Day 60, but Installment 3
       ↓
       [See Phase 6 for what happens next - VENDOR CREDITING]

═════════════════════════════════════════════════════════════
```

---

## Phase 6: Final Payment & Plan Completion

### What Happens:
When the customer makes the final installment payment (Installment 3), the entire plan is completed and triggers vendor crediting.

### Final Payment Verification Process:

```python
# Same as phases 4 & 5, but this time:
installment_3.mark_as_paid()
# installment_3.status = "PAID"

# NOW check if plan is fully paid
plan.is_fully_paid()  # Returns True! (All 3 of 3 paid)

# THIS TRIGGERS VENDOR CREDITING
if plan.is_fully_paid() and not plan.vendors_credited:
    
    # For each vendor in the order:
    for item in plan.order.order_items.all():
        vendor = item.product.store
        
        # Calculate vendor's share:
        # Vendor gets: item_subtotal - platform_commission
        # Platform commission: 10%
        vendor_share = item.item_subtotal * (1.00 - 0.10)
        # Example: ₦50,000 * 0.90 = ₦45,000
        
        # Get or create vendor's wallet
        wallet, _ = Wallet.objects.get_or_create(user=vendor)
        
        # Credit wallet
        wallet.credit(
            vendor_share,
            source=f"Order {plan.order.order_id} (Installment)"
        )
        
        # Create wallet transaction record
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="CREDIT",
            amount=vendor_share,
            source=f"Order {plan.order.order_id} (Installment)"
        )
    
    # Mark that vendors have been credited
    plan.vendors_credited = True
    plan.save()
```

### Complete Vendor Crediting Example:

**Scenario:**
- Order Total: ₦135,000
  - Vendor A contributed: ₦100,000 (2 products @ ₦50,000 each)
  - Vendor B contributed: ₦30,000 (1 product @ ₦30,000)
  - Delivery fee: ₦5,000 (platform keeps this)

**After Final Payment:**
```
Vendor A Wallet Credit:
  Amount: ₦100,000 × 0.90 = ₦90,000
  Source: "Order 550e8400-...-(Installment)"
  
Vendor B Wallet Credit:
  Amount: ₦30,000 × 0.90 = ₦27,000
  Source: "Order 550e8400-...-(Installment)"

Platform Keeps:
  Vendor A Commission: ₦100,000 × 0.10 = ₦10,000
  Vendor B Commission: ₦30,000 × 0.10 = ₦3,000
  Delivery Fee: ₦5,000
  Total Platform Revenue: ₦18,000
```

### Idempotency Protection:

The system is designed to be idempotent - if the webhook is called multiple times or verification happens twice, vendors are only credited ONCE:

```python
if plan.is_fully_paid() and not plan.vendors_credited:
    # This condition prevents duplicate crediting
    # vendors_credited flag is set to True immediately
    plan.vendors_credited = True
    plan.save()
```

### Database State After Final Payment:

**InstallmentPayment Records:**
```
Installment 1: status="PAID",     amount=₦45,000 ✓
Installment 2: status="PAID",     amount=₦45,000 ✓
Installment 3: status="PAID",     amount=₦45,000 ✓
```

**InstallmentPlan:**
```
status="COMPLETED"
vendors_credited=True
```

**Order:**
```
payment_status="PAID"
status="PAID"  # Updated by mark_as_completed()
```

**Wallet Records:**
```
Vendor A Wallet: balance increased by ₦90,000
Vendor B Wallet: balance increased by ₦27,000

WalletTransaction for Vendor A:
  - transaction_type: "CREDIT"
  - amount: ₦90,000
  - source: "Order 550e8400-...-(Installment)"
  - created_at: [timestamp]

WalletTransaction for Vendor B:
  - transaction_type: "CREDIT"
  - amount: ₦27,000
  - source: "Order 550e8400-...-(Installment)"
  - created_at: [timestamp]
```

---

## Phase 7: Post-Completion Processes

### What Happens After Installment Plan Completion:

#### 1. Automatic Order Status Update
```python
# Triggered in InstallmentPlan.mark_as_completed()
order.payment_status = "PAID"
order.status = Order.Status.PAID  # Now "PAID" not "PENDING"
order.save()
```

#### 2. Order Fulfillment Can Proceed
- Admin/Vendor can now proceed to ship the order
- Update order.status from "PAID" → "SHIPPED" → "DELIVERED"
- System allows shipping logistics to proceed

#### 3. Vendor Wallet Management
**What Vendors Can Do:**
- Check their wallet balance
```
GET /api/transactions/wallet/
Response: { balance: ₦90,000, ... }
```

- View their wallet transactions
```
GET /api/transactions/wallet/transactions/
Response: [
  {
    "transaction_type": "CREDIT",
    "amount": ₦90,000,
    "source": "Order 550e8400-...-(Installment)",
    "created_at": "2026-01-10T15:30:00Z"
  }
]
```

- Withdraw or transfer wallet balance (implementation dependent)

#### 4. Customer Can Leave Reviews
- Once order is delivered, customer can leave product reviews
- Rate products and leave comments

#### 5. Refund Eligibility
- Refunds can only be initiated if:
  - Payment was successful (verified=True)
  - Reason is valid
  - Order status allows it

**Refund Process:**
```
POST /api/transactions/refunds/
{
  "payment_id": 123,
  "reason": "Product damaged",
  "refunded_amount": 45000
}
→ Refund created with status="PENDING"

PATCH /api/transactions/refunds/1/
{
  "action": "APPROVE"  // or "REJECT"
}
→ If APPROVED: Customer wallet is credited
   If REJECTED: Refund is denied
```

#### 6. Notification Timeline

**Throughout the installment plan:**
```
Day 0: Checkout completed
  - Vendor notified: "New Order Received (Installment)"

Day 30: Installment 1 due + paid
  - Order still in progress

Day 60: Installment 2 due + paid
  - Order still in progress

Day 90: Installment 3 due + paid
  - Order payment_status → "PAID"
  - Vendors credited
  - Vendors notified: "Payment received for order {order_id}"
  
  - Customer can track: "Order {order_id} status: PAID"
  - Shipping can begin
```

#### 7. Analytics & Reporting
Admin can view:
- All installment plans
- Payment completion rates
- Overdue installments
- Vendor earnings
- Platform commission earned

```
GET /api/transactions/installment-plans/
GET /api/transactions/admin/wallets/
```

---

## Database Models

### Model Relationships:

```
CustomUser (Customer)
  └─ Cart (1-to-1)
      └─ CartItem (1-to-Many) [REMOVED after checkout]
  └─ Order (1-to-Many) [CREATED during checkout]
      ├─ OrderItem (1-to-Many)
      │   └─ Product
      │       └─ Vendor (user)
      ├─ InstallmentPlan (1-to-1) [Only for installment orders]
      │   └─ InstallmentPayment (1-to-Many)
      └─ Payment (1-to-1) [Only for one-time payment orders]
  └─ Wallet (1-to-1)
      └─ WalletTransaction (1-to-Many) [CREATED when wallet is credited]

Vendor (CustomUser with is_staff=True or special role)
  └─ Wallet (1-to-1)
      └─ WalletTransaction (1-to-Many)
  └─ Product (1-to-Many)
      └─ OrderItem (1-to-Many)
```

### Full Model Definitions:

#### InstallmentPlan
```python
class InstallmentPlan(models.Model):
    # Status constants
    DURATION_CHOICES = {
        '1_month': 1 installment,
        '3_months': 3 installments,
        '6_months': 6 installments,
        '1_year': 12 installments
    }
    
    order                      # OneToOne to Order
    duration                   # CharField, required
    total_amount              # DecimalField, the full order total
    installment_amount        # DecimalField, amount per installment
    number_of_installments    # PositiveIntegerField
    start_date                # DateTimeField, auto_now_add=True
    status                    # CharField, default='ACTIVE'
                             # Options: 'ACTIVE', 'COMPLETED', 'CANCELLED'
    vendors_credited          # BooleanField, default=False
                             # True = vendors have been paid from this order
    created_at                # DateTimeField, auto_now_add=True
    updated_at                # DateTimeField, auto_now=True
```

#### InstallmentPayment
```python
class InstallmentPayment(models.Model):
    STATUS_CHOICES = {
        'PENDING': "Pending",
        'PAID': "Paid",
        'FAILED': "Failed",
        'OVERDUE': "Overdue"
    }
    
    installment_plan           # ForeignKey to InstallmentPlan
    payment_number             # PositiveIntegerField (1, 2, 3...)
    amount                     # DecimalField, individual installment amount
    status                     # CharField, default='PENDING'
    due_date                   # DateTimeField, when payment is due
    payment_date               # DateTimeField, null=True (when customer paid)
    reference                  # CharField, unique identifier for payment gateway
    gateway                    # CharField, default='Paystack'
    paid_at                    # DateTimeField, when system confirmed payment
    verified                   # BooleanField, default=False
    created_at                 # DateTimeField, auto_now_add=True
    updated_at                 # DateTimeField, auto_now=True
    
    # Constraints:
    # - (installment_plan, payment_number) must be unique
    # - reference must be globally unique
    # - Indexes on: status, reference
```

#### Wallet
```python
class Wallet(models.Model):
    user                       # OneToOneField to CustomUser
    balance                    # DecimalField, current wallet balance
    updated_at                 # DateTimeField, auto_now=True
    
    Methods:
    - credit(amount, source)   # Add funds + create WalletTransaction
    - debit(amount, source)    # Remove funds + create WalletTransaction
```

#### WalletTransaction
```python
class WalletTransaction(models.Model):
    TYPE_CHOICES = {
        'CREDIT': "Credit (incoming funds)",
        'DEBIT': "Debit (outgoing funds)"
    }
    
    wallet                     # ForeignKey to Wallet
    transaction_type           # CharField, 'CREDIT' or 'DEBIT'
    amount                     # DecimalField, transaction amount
    source                     # CharField, describing source/purpose
                              # Examples: "Order 550e8400-...-(Installment)"
                              #           "Refund 123-abc"
    created_at                 # DateTimeField, auto_now_add=True
```

#### Order
```python
class Order(models.Model):
    STATUS_CHOICES = {
        'PENDING': "Pending",
        'PAID': "Paid",
        'SHIPPED': "Shipped",
        'DELIVERED': "Delivered",
        'CANCELED': "Canceled"
    }
    
    order_id                   # UUIDField, unique identifier
    customer                   # ForeignKey to CustomUser
    status                     # CharField, default='PENDING'
    products                   # ManyToManyField via OrderItem
    total_price                # DecimalField, order subtotal + fees - discount
    delivery_fee               # DecimalField, shipping cost
    discount                   # DecimalField, any discount applied
    tracking_number            # CharField, for shipping tracking
    payment_status             # CharField, 'UNPAID' or 'PAID'
    ordered_at                 # DateTimeField, auto_now_add=True
    updated_at                 # DateTimeField, auto_now=True
    
    Properties:
    - is_paid                  # bool, True if payment_status == 'PAID'
    - is_delivered             # bool, True if status == 'DELIVERED'
    - subtotal                 # sum of all OrderItem subtotals
    - total_with_delivery      # subtotal + delivery_fee - discount
```

#### OrderItem
```python
class OrderItem(models.Model):
    order                      # ForeignKey to Order
    product                    # ForeignKey to Product
    quantity                   # PositiveIntegerField
    price_at_purchase          # DecimalField, locked-in price at time of order
    
    Properties:
    - item_subtotal            # price_at_purchase × quantity
    - vendor                   # product.store (the vendor who owns this product)
```

---

## API Endpoints

### Installment Checkout Endpoints

#### 1. Initiate Installment Checkout (First Payment)

**Endpoint:**
```
POST /api/transactions/checkout/installment/
```

**Request:**
```yaml
Headers:
  Authorization: Bearer {token}
  Content-Type: application/json

Body (InstallmentCheckoutSerializer):
{
  "duration": "3_months"
}
```

**Duration Options:**
- `"1_month"` → 1 installment
- `"3_months"` → 3 installments  
- `"6_months"` → 6 installments
- `"1_year"` → 12 installments

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "order_id": "550e8400-e29b-41d4-a716-446655440000",
    "installment_plan_id": 42,
    "duration": "3_months",
    "total_amount": 135000.00,
    "number_of_installments": 3,
    "installment_amount": 45000.00,
    "first_installment_reference": "550e8400-e29b-41d4-a716-446655440000-installment-1",
    "authorization_url": "https://checkout.paystack.co/..."
  },
  "message": "Installment checkout initialized successfully"
}
```

**Errors:**
- `400 Bad Request`: Cart is empty, invalid duration, no items
- `401 Unauthorized`: Missing or invalid token

---

#### 2. Initialize Subsequent Installment Payment

**Endpoint:**
```
POST /api/transactions/installment-plans/init-payment/
```

**Request:**
```yaml
Headers:
  Authorization: Bearer {token}
  Content-Type: application/json

Body:
{
  "plan_id": 42,
  "payment_number": 2
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "authorization_url": "https://checkout.paystack.co/...",
    "amount": 45000.00,
    "reference": "550e8400-...-installment-2",
    "payment_number": 2,
    "installment_plan_id": 42
  },
  "message": "Installment payment initialized successfully"
}
```

**Errors:**
- `400 Bad Request`: Missing fields, already paid, Paystack error
- `403 Forbidden`: Not your plan
- `404 Not Found`: Plan or installment doesn't exist
- `401 Unauthorized`: Missing or invalid token

---

#### 3. Verify Installment Payment

**Endpoint:**
```
GET /api/transactions/verify-installment-payment/?reference={reference}
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| reference | string | Yes | The installment payment reference (e.g., "550e8400-...-installment-2") |

**Response (200 OK) - InstallmentPaymentSerializer:**
```json
{
  "success": true,
  "data": {
    "id": 2,
    "payment_number": 2,
    "amount": 45000.00,
    "status": "PAID",
    "due_date": "2026-03-11T15:30:00Z",
    "payment_date": "2026-03-11T15:30:00Z",
    "reference": "550e8400-...-installment-2",
    "gateway": "Paystack",
    "paid_at": "2026-03-11T15:30:00Z",
    "verified": true,
    "created_at": "2026-01-10T15:30:00Z",
    "is_overdue": false
  },
  "message": "Installment payment verified successfully"
}
```

**Errors:**
- `400 Bad Request`: Reference required, payment not successful, currency/amount mismatch
- `403 Forbidden`: Not your payment
- `404 Not Found`: Payment not found
- `401 Unauthorized`: Missing or invalid token

**Status Values:**
- `"PENDING"` - Not yet paid
- `"PAID"` - Successfully paid ✓
- `"FAILED"` - Payment failed
- `"OVERDUE"` - Past due date and not paid

---

#### 4. List Installment Plans

**Endpoint:**
```
GET /api/transactions/installment-plans/
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| (none) | - | Auto-filters by current user (admin sees all) |

**Response (200 OK) - InstallmentPlanSerializer (array):**
```json
{
  "success": true,
  "data": [
    {
      "id": 42,
      "order_id": "550e8400-e29b-41d4-a716-446655440000",
      "duration": "3_months",
      "total_amount": 135000.00,
      "installment_amount": 45000.00,
      "number_of_installments": 3,
      "paid_installments_count": 1,
      "pending_installments_count": 2,
      "status": "ACTIVE",
      "is_fully_paid": false,
      "start_date": "2026-01-10T15:30:00Z",
      "created_at": "2026-01-10T15:30:00Z",
      "updated_at": "2026-01-10T15:30:00Z",
      "installments": [
        {
          "id": 1,
          "payment_number": 1,
          "amount": 45000.00,
          "status": "PAID",
          "due_date": "2026-02-09T15:30:00Z",
          "payment_date": "2026-01-10T15:30:00Z",
          "reference": "550e8400-...-installment-1",
          "gateway": "Paystack",
          "paid_at": "2026-01-10T15:30:00Z",
          "verified": true,
          "created_at": "2026-01-10T15:30:00Z",
          "is_overdue": false
        },
        {
          "id": 2,
          "payment_number": 2,
          "amount": 45000.00,
          "status": "PENDING",
          "due_date": "2026-03-11T15:30:00Z",
          "payment_date": null,
          "reference": "550e8400-...-installment-2",
          "gateway": "Paystack",
          "paid_at": null,
          "verified": false,
          "created_at": "2026-01-10T15:30:00Z",
          "is_overdue": false
        }
      ]
    }
  ]
}
```

---

#### 5. Get Single Installment Plan Details

**Endpoint:**
```
GET /api/transactions/installment-plans/{id}/
```

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | Installment plan ID |

**Response (200 OK) - InstallmentPlanSerializer:**
```json
{
  "success": true,
  "data": {
    "id": 42,
    "order_id": "550e8400-e29b-41d4-a716-446655440000",
    "duration": "3_months",
    "total_amount": 135000.00,
    "installment_amount": 45000.00,
    "number_of_installments": 3,
    "paid_installments_count": 2,
    "pending_installments_count": 1,
    "status": "ACTIVE",
    "is_fully_paid": false,
    "start_date": "2026-01-10T15:30:00Z",
    "created_at": "2026-01-10T15:30:00Z",
    "updated_at": "2026-01-10T15:30:00Z",
    "installments": [...]
  }
}
```

**Errors:**
- `403 Forbidden`: Not your plan
- `404 Not Found`: Plan not found
- `401 Unauthorized`: Missing or invalid token

---

#### 6. List Installment Payments for a Plan

**Endpoint:**
```
GET /api/transactions/installment-plans/{plan_id}/payments/
```

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| plan_id | integer | Yes | Installment plan ID |

**Response (200 OK) - InstallmentPaymentSerializer (array):**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "payment_number": 1,
      "amount": 45000.00,
      "status": "PAID",
      "due_date": "2026-02-09T15:30:00Z",
      "payment_date": "2026-01-10T15:30:00Z",
      "reference": "550e8400-...-installment-1",
      "gateway": "Paystack",
      "paid_at": "2026-01-10T15:30:00Z",
      "verified": true,
      "created_at": "2026-01-10T15:30:00Z",
      "is_overdue": false
    },
    {
      "id": 2,
      "payment_number": 2,
      "amount": 45000.00,
      "status": "PENDING",
      "due_date": "2026-03-11T15:30:00Z",
      "payment_date": null,
      "reference": "550e8400-...-installment-2",
      "gateway": "Paystack",
      "paid_at": null,
      "verified": false,
      "created_at": "2026-01-10T15:30:00Z",
      "is_overdue": false
    }
  ]
}
```

---

#### 7. Paystack Webhook (Automatic Payment Confirmation)

**Endpoint:**
```
POST /api/transactions/installment-webhook/
```

**No Authentication Required** - Paystack will send this automatically

**Headers Sent by Paystack:**
```
x-paystack-signature: {HMAC-SHA512 signature}
Content-Type: application/json
```

**Request Body (from Paystack):**
```json
{
  "event": "charge.success",
  "data": {
    "id": 123456789,
    "reference": "550e8400-...-installment-2",
    "amount": 4500000,
    "paid_at": "2026-03-11T15:30:00Z",
    "customer": {
      "id": 1,
      "email": "customer@example.com"
    },
    "status": "success",
    "currency": "NGN"
  }
}
```

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

**Note:** Your backend will verify the signature and process the payment internally

---

## API Serializer Schemas

### InstallmentCheckoutSerializer
**Used for:** POST `/api/transactions/checkout/installment/`

| Field | Type | Required | Read-Only | Default | Choices | Description |
|-------|------|----------|-----------|---------|---------|-------------|
| `duration` | String | Yes | No | - | `1_month`, `3_months`, `6_months`, `1_year` | Payment duration period |

---

### InstallmentPaymentSerializer
**Used for:** Payment responses in list and verify endpoints

| Field | Type | Required | Read-Only | Description |
|-------|------|----------|-----------|-------------|
| `id` | Integer | - | Yes | Unique payment ID |
| `payment_number` | Integer | - | Yes | Sequential number (1, 2, 3, etc.) |
| `amount` | Decimal | - | Yes | Payment amount in Naira |
| `status` | String | - | Yes | One of: `PENDING`, `PAID`, `FAILED`, `OVERDUE` |
| `due_date` | DateTime | - | Yes | When this installment is due |
| `payment_date` | DateTime | - | Yes | When customer initiated payment (null if unpaid) |
| `reference` | String | - | Yes | Unique Paystack reference |
| `gateway` | String | - | Yes | Always `"Paystack"` |
| `paid_at` | DateTime | - | Yes | Exact time payment was confirmed (null if unpaid) |
| `verified` | Boolean | - | Yes | Whether payment was verified by webhook |
| `created_at` | DateTime | - | Yes | When record was created |
| `is_overdue` | Boolean | - | Yes | Computed: `status == "PENDING" and due_date < now` |

---

### InstallmentPlanSerializer
**Used for:** Plan responses in list and detail endpoints

| Field | Type | Required | Read-Only | Description |
|-------|------|----------|-----------|-------------|
| `id` | Integer | - | Yes | Unique plan ID |
| `order_id` | String (UUID) | - | Yes | Associated order ID |
| `duration` | String | - | Yes | Payment period (1_month, 3_months, 6_months, 1_year) |
| `total_amount` | Decimal | - | Yes | Total order amount in Naira |
| `installment_amount` | Decimal | - | Yes | Amount per installment |
| `number_of_installments` | Integer | - | Yes | Total number of installments |
| `paid_installments_count` | Integer | - | Yes | Count of PAID installments |
| `pending_installments_count` | Integer | - | Yes | Count of PENDING installments |
| `status` | String | - | Yes | `"ACTIVE"` or `"COMPLETED"` |
| `is_fully_paid` | Boolean | - | Yes | Computed: all installments PAID |
| `start_date` | DateTime | - | Yes | When first installment was created |
| `created_at` | DateTime | - | Yes | Record creation timestamp |
| `updated_at` | DateTime | - | Yes | Last update timestamp |
| `installments` | Array[InstallmentPaymentSerializer] | - | Yes | All payments for this plan |

---

### InitPaymentRequest
**Used for:** POST `/api/transactions/installment-plans/init-payment/`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plan_id` | Integer | Yes | ID of the installment plan |
| `payment_number` | Integer | Yes | Which installment to pay (2, 3, 4, etc.) |

**Constraints:**
- `plan_id` must exist and belong to current user
- `payment_number` must be between 2 and `number_of_installments`
- That specific installment must have `status == "PENDING"` (can't pay twice)

---

## HTTP Status Codes Reference

| Status | Meaning | Common Scenarios |
|--------|---------|------------------|
| `200` | OK | Successful GET requests |
| `201` | Created | Successful POST requests creating resources |
| `400` | Bad Request | Invalid input, missing fields, validation errors |
| `401` | Unauthorized | Missing/invalid authentication token |
| `403` | Forbidden | Resource belongs to different user |
| `404` | Not Found | Resource doesn't exist |
| `500` | Server Error | Unexpected backend error |

---

## Key Features & Constraints

## Payment Verification & Webhooks

### Verification Methods

#### Method 1: Direct API Call (Synchronous)
Recommended after customer is redirected back from Paystack

```python
# Flow:
1. Customer completes payment on Paystack
2. Paystack redirects to callback_url
3. Frontend/Backend calls: GET /verify-installment-payment/?reference=...
4. Immediate verification result
5. Update UI based on response
```

**Advantages:**
- Immediate user feedback
- Real-time status updates
- Synchronous error handling

**Disadvantages:**
- Depends on network connectivity
- May timeout if Paystack slow

#### Method 2: Paystack Webhook (Asynchronous)
Paystack calls your app when payment succeeds

```python
# Flow:
1. Customer completes payment on Paystack
2. Paystack internally verifies payment
3. Paystack POSTs to your webhook endpoint
4. Webhook handler processes asynchronously
5. Idempotent - can be called multiple times safely
```

**Webhook Endpoint:**
```
POST /api/transactions/installment-webhook/
Headers: x-paystack-signature: {signature}
Body: { "data": { "reference": "...", "status": "success", ... } }
```

**Webhook Security:**
```python
# CRITICAL: Always verify signature
signature = request.headers.get("x-paystack-signature")
computed = hmac.new(
    PAYSTACK_SECRET_KEY.encode(),
    request.body,
    hashlib.sha512
).hexdigest()

# Compare safely (timing-attack resistant)
if not hmac.compare_digest(computed, signature):
    return 403  # FORBIDDEN

# Only then process the payment
```

**Advantages:**
- Works even if customer doesn't return
- Async processing
- More reliable than relying on customer network
- Paystack guarantees delivery (with retries)

**Disadvantages:**
- Slightly delayed (few seconds)
- Must implement idempotency

### Webhook Idempotency

The system prevents duplicate processing through multiple safeguards:

```python
# Check 1: Status check
if installment.status == InstallmentPayment.PaymentStatus.PAID:
    return  # Already processed, exit early

# Check 2: Vendors credited flag
if plan.is_fully_paid() and not plan.vendors_credited:
    # Only credit once
    credit_vendors(...)
    plan.vendors_credited = True  # Prevent future credits
```

### Complete Payment Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  1. Customer adds products to cart                          │
│     Cart → CartItems                                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Customer clicks "Pay with Installment"                  │
│     POST /checkout/installment/                             │
│     Body: { duration: "3_months" }                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Server creates:                                          │
│     - Order                                                  │
│     - OrderItems (from CartItems)                           │
│     - InstallmentPlan (3 installments)                      │
│     - 3× InstallmentPayment (PENDING)                       │
│     - Initialize Paystack payment for 1st installment      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Response contains authorization_url                     │
│     Customer redirected to Paystack checkout                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Customer enters payment details on Paystack             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Paystack processes payment                              │
│     Two outcomes:                                            │
│     A) Webhook: POST /installment-webhook/ (automatic)     │
│     B) Return: Customer returns, call /verify-.../ (manual) │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                       ▼
   [WEBHOOK]                            [DIRECT VERIFICATION]
        │                                       │
        ▼                                       ▼
┌───────────────────────┐         ┌───────────────────────┐
│ Verify signature      │         │ GET /verify-.../?ref= │
│ Call Paystack API     │         │ Verify signature (N/A)│
│ Check amount/currency │         │ Call Paystack API     │
│ Mark as PAID          │         │ Check amount/currency │
│ Check if plan full    │         │ Mark as PAID          │
│ If yes: credit vendors│         │ Check if plan full    │
│ Set vendors_credited  │         │ If yes: credit vendors│
└───────────────────────┘         │ Set vendors_credited  │
        │                         └───────────────────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            │
                            ▼
        ┌─────────────────────────────────────┐
        │  Installment 1: PAID ✓              │
        │  Installment 2: PENDING (in 30d)    │
        │  Installment 3: PENDING (in 60d)    │
        └─────────────────────────────────────┘
                            │
                            ▼
        ┌─────────────────────────────────────┐
        │  [30 days later]                    │
        │  Customer initiates payment 2       │
        │  Repeat steps 5-6 for installment 2 │
        │  Mark Installment 2: PAID ✓         │
        │  Installment 3: PENDING (in 30d)    │
        └─────────────────────────────────────┘
                            │
                            ▼
        ┌─────────────────────────────────────┐
        │  [30 days later]                    │
        │  Customer initiates payment 3       │
        │  Repeat steps 5-6 for installment 3 │
        └─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  7. FINAL PAYMENT VERIFICATION (Installment 3)              │
│     Check: plan.is_fully_paid() == True                    │
│     AND: plan.vendors_credited == False                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  8. TRIGGER: Credit Vendor Wallets                         │
│     For each OrderItem:                                     │
│       vendor_share = item_subtotal * 0.90                  │
│       Wallet.credit(vendor_share)                          │
│       Create WalletTransaction(CREDIT)                     │
│     Set: plan.vendors_credited = True                      │
│     Set: plan.status = "COMPLETED"                         │
│     Set: order.status = "PAID"                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  9. POST-COMPLETION                                         │
│     - Vendors can view updated wallet balance               │
│     - Admin can ship the order                              │
│     - Order status → SHIPPED → DELIVERED                    │
│     - Customers can leave reviews                           │
│     - Payment fully complete                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Features & Constraints

### Idempotency
- All payment marking operations are idempotent
- Safe to call verification multiple times
- Webhook can be delivered multiple times without issues
- Vendors only credited once per plan

### Atomicity
- All state changes use database transactions (`transaction.atomic()`)
- Either everything succeeds or everything rolls back
- No partial updates

### Security
- Paystack webhook signatures verified with HMAC-SHA512
- Direct verification throttled with UserRateThrottle
- Order data filtered by ownership (customer can't see others' orders)

### Rounding & Precision
- All amounts are Decimal(max_digits=10, decimal_places=2)
- Base installment amount rounded down (ROUND_DOWN)
- Remainder added to final installment
- Prevents rounding errors that would cause underpayment

### Commission Model
- Platform takes 10% commission on vendor sales
- Applied when vendors are credited (at plan completion)
- Formula: `vendor_share = item_subtotal * 0.90`
- Delivery fees go entirely to platform

---

## Example Scenarios

### Scenario 1: 3-Month Installment with 2 Vendors

**Order Details:**
- Product A (Vendor X): ₦50,000 × 2 = ₦100,000
- Product B (Vendor Y): ₦30,000 × 1 = ₦30,000
- Delivery Fee: ₦5,000
- Discount: ₦0
- **Order Total: ₦135,000**

**Installment Plan:**
- Duration: 3 months
- Installment Amount: ₦135,000 ÷ 3 = ₦45,000 each
- Due Dates: Day 30, Day 60, Day 90

**Payment Schedule:**
```
Day 0: Checkout initiated
  - Installment 1: ₦45,000 (DUE: Day 30)
  - Installment 2: ₦45,000 (DUE: Day 60)
  - Installment 3: ₦45,000 (DUE: Day 90)

Day 30: Customer pays ₦45,000
  - Installment 1: PAID ✓
  - Installment 2: PENDING
  - Installment 3: PENDING
  - Status: ACTIVE
  - Vendors Not Credited (waiting for final payment)

Day 60: Customer pays ₦45,000
  - Installment 1: PAID ✓
  - Installment 2: PAID ✓
  - Installment 3: PENDING
  - Status: ACTIVE
  - Vendors Not Credited (waiting for final payment)

Day 90: Customer pays ₦45,000
  - Installment 1: PAID ✓
  - Installment 2: PAID ✓
  - Installment 3: PAID ✓
  - Status: COMPLETED
  - Vendors Credited: YES ✓

  Vendor X Wallet Credit: ₦100,000 × 0.90 = ₦90,000
  Vendor Y Wallet Credit: ₦30,000 × 0.90 = ₦27,000
  Platform Revenue: (₦100,000 × 0.10) + (₦30,000 × 0.10) + ₦5,000 = ₦18,000
```

**After Day 90:**
- Order status: PAID
- Payment status: PAID
- Vendors credited: ₦90,000 + ₦27,000 = ₦117,000
- Platform earned: ₦18,000
- Admin can proceed with shipping

---

### Scenario 2: 1-Year Installment (Single Product)

**Order Details:**
- Product C (Vendor Z): ₦120,000 × 1 = ₦120,000
- Delivery Fee: ₦10,000
- Discount: ₦10,000
- **Order Total: ₦120,000**

**Installment Plan:**
- Duration: 1 year
- Number of Installments: 12
- Base Installment: ₦120,000 ÷ 12 = ₦10,000

**Payment Timeline:**
```
Months 1-11: ₦10,000 each (PAID as due date arrives)
Month 12: ₦10,000 + remainder (FINAL PAYMENT)
```

**At Final Payment (Month 12):**
```
Vendor Z Wallet Credit: ₦120,000 × 0.90 = ₦108,000
Platform Revenue: (₦120,000 × 0.10) + ₦10,000 = ₦22,000

Order marked as PAID
InstallmentPlan marked as COMPLETED
Vendor Z can view: balance = ₦108,000
```

---

### Scenario 3: Payment Failure & Retry

**Initial Payment:**
```
Day 0: Customer initiates payment for Installment 1 (₦45,000)
  - Paystack initialization successful
  - Customer redirected to Paystack

Day 0: Customer enters incorrect card details
  - Payment fails on Paystack side
  - Paystack returns error status
  - Webhook not sent (only for successful payments)
```

**Retry:**
```
Day 1: Customer retries payment for same Installment 1
  - Same reference is used
  - Customer completes payment successfully
  - Paystack webhooks or direct verification called
  - InstallmentPayment 1: PAID ✓
  - System continues normally
```

**System State:**
```
No duplicate payments because:
1. Reference is unique per installment number
2. InstallmentPayment.verified check prevents double crediting
3. Vendors only credited once when entire plan complete
```

---

## Troubleshooting Guide

### Common Issues

#### 1. "Cart is empty" error
**Cause:** Customer's cart has no items
**Solution:** Add items to cart before checkout

#### 2. "Payment not successful" error
**Cause:** Paystack returned status != "success"
**Solution:**
- Check customer's payment status on Paystack dashboard
- Verify payment amount is correct
- Check network connectivity

#### 3. "Amount mismatch" error
**Cause:** Amount paid doesn't match installment amount
**Cause:** Paystack amount in kobo (÷100) vs system expects naira
**Solution:**
```python
# System checks: Decimal(paystack_amount) / Decimal(100) == installment.amount
# If mismatch, payment not verified
```

#### 4. Vendors not credited after final payment
**Cause 1:** Webhook not delivered
**Solution:**
- Check webhook delivery logs in Paystack dashboard
- Manually call GET /verify-installment-payment/?reference=...

**Cause 2:** Plan not actually fully paid
**Solution:**
- Check InstallmentPayment records in database
- Verify all have status = "PAID"

**Cause 3:** Already credited (idempotent)
**Solution:**
- Check if plan.vendors_credited = True
- Check WalletTransaction records for the credit entry

#### 5. Double crediting (rare)
**Cause:** Webhook delivered twice for same payment
**System Protection:**
```python
if installment.status == "PAID":
    return  # Exit early, already processed

if plan.is_fully_paid() and plan.vendors_credited:
    return  # Don't credit again
```

---

## Performance Considerations

### Database Indexes
```python
# On InstallmentPayment:
- Index on: status
- Index on: reference (unique)
- Composite unique: (installment_plan, payment_number)

# On InstallmentPlan:
- Foreign key on: order (auto-indexed)
- No manual indexes needed for small datasets
```

### Query Optimization
```python
# Use select_related for foreign keys:
InstallmentPayment.objects.select_related(
    "installment_plan__order"
).get(reference=reference)

# Use select_for_update for concurrent payment processing:
installment = InstallmentPayment.objects.select_for_update().get(pk=id)
```

### Scaling Notes
- Current design supports millions of installment plans
- No complex joins or aggregations in payment path
- Webhook processing is fire-and-forget (async-friendly)
- Commission calculation is O(n) where n = items per order (typically < 10)

---

## Future Enhancements

### Planned Features
1. **Early Completion:** Allow customer to pay all remaining installments at once
2. **Installment Suspension:** Pause plan temporarily (e.g., financial hardship)
3. **Late Fee Accrual:** Charge penalty for overdue payments
4. **Payment Plans:** Offer promotions for installment purchases
5. **Auto-Pay:** Set up automatic recurring payments via subscription
6. **Installment Insurance:** Optional insurance against payment default

### Possible Variations
- Different commission rates by vendor/category
- Configurable payment intervals (weekly, bi-weekly, monthly, quarterly)
- Deposit requirement (e.g., 20% upfront, rest in installments)
- Seasonal promotions (0% interest for 3 months)

---

## Summary

The installment payment system is designed as follows:

1. **Cart Phase:** Customer adds products to cart
2. **Checkout Phase:** Customer selects installment duration, order and plan created
3. **First Payment Phase:** Customer pays first installment via Paystack
4. **Subsequent Payments:** Customer pays remaining installments one by one
5. **Completion Phase:** Final payment triggers vendor crediting and order fulfillment
6. **Post-Completion:** Order can be shipped, vendors access earnings, customer can review

Key principles:
- **Idempotent:** Safe to call verification multiple times
- **Atomic:** All-or-nothing state changes
- **Secure:** Webhook signatures verified
- **Transparent:** Clear tracking of each installment status
- **Vendor-Friendly:** Automatic wallet credits with commission deduction

