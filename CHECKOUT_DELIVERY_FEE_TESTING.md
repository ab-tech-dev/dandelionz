# Checkout Process with Delivery Fee Toggle - Complete Verification

## Overview
The checkout system has been updated to use a configurable toggle `ENFORCE_DELIVERY_FEE_ON_CHECKOUT` that controls whether delivery fees should block the checkout process.

**Default Setting:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False` (Delivery fees do NOT block checkout)

---

## Setting Configuration

### In `.env` file:
```
# Set to True to require delivery coordinates before checkout
# Set to False to allow checkout even without delivery fee calculation
ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False
```

### In `e_commerce_api/settings.py`:
```python
ENFORCE_DELIVERY_FEE_ON_CHECKOUT = os.getenv('ENFORCE_DELIVERY_FEE_ON_CHECKOUT', 'False').lower() in ('true', '1', 'yes')
```

---

## Complete Checkout Flow

### A. Single Payment Checkout (`POST /api/transactions/checkout/`)

#### Step 1: Validation - Cart Checks
✅ **Status:** REQUIRED (Always validates)
- Check if cart exists
- Check if cart has items
- Returns `HTTP_400_BAD_REQUEST` if empty

#### Step 2: Validation - Customer Profile
✅ **Status:** REQUIRED (Always validates)
- Check if user has customer_profile
- Returns `HTTP_400_BAD_REQUEST` if missing

#### Step 3: Validation - Shipping Coordinates (CONDITIONAL)
🔀 **Status:** DEPENDS ON `ENFORCE_DELIVERY_FEE_ON_CHECKOUT`

**IF `ENFORCE_DELIVERY_FEE_ON_CHECKOUT = True`:**
```
├─ Check customer_profile.shipping_latitude exists
├─ Check customer_profile.shipping_longitude exists
└─ Returns HTTP_400_BAD_REQUEST if missing (BLOCKS CHECKOUT)
```

**IF `ENFORCE_DELIVERY_FEE_ON_CHECKOUT = False`:**
```
├─ Check customer_profile.shipping_latitude exists
├─ Check customer_profile.shipping_longitude exists
└─ Logs info message but CONTINUES CHECKOUT (allows without coordinates)
```

#### Step 4: Create Order (In Atomic Transaction)
✅ **Status:** Creates order with default delivery_fee = 0
- Order created in PENDING status
- Order ID generated

#### Step 5: Convert Cart Items to Order Items
✅ **Status:** Required, copies items with discounted prices
- Creates OrderItem for each CartItem
- Uses product.get_final_price (handles discounts)

#### Step 6: Retrieve Delivery Coordinates
🔄 **Status:** Optional (Wrapped in try-catch)
```
├─ Get vendor coordinates from first product's store
│  ├─ If vendor exists: store_latitude, store_longitude
│  └─ If missing: continues silently
├─ Get customer coordinates from customer_profile
│  ├─ If exists: shipping_latitude, shipping_longitude
│  └─ If missing: continues silently
└─ If any retrieval fails: continues (pass statement)
```

#### Step 7: Calculate Delivery Fee (OPTIONAL)
🔄 **Status:** Only if BOTH coordinate sets available
```
IF (order.restaurant_lat AND order.restaurant_lng AND 
    order.customer_lat AND order.customer_lng):
    ├─ Call DeliveryFeeCalculator
    │  ├─ Calls Radar Distance API
    │  ├─ Calculates: distance, duration, distance_miles
    │  └─ Calculates fee based on formula:
    │     fee = base_fee + (distance_miles * per_mile_rate)
    │     fee = min(fee, max_fee)
    ├─ Updates order.delivery_fee
    └─ Saves to database
ELSE:
    ├─ Logs warning about incomplete coordinates
    └─ Continues with delivery_fee = 0 (DEFAULT)

IF delivery fee calculation fails:
    ├─ Logs warning: "Delivery fee calculation failed"
    └─ Continues checkout (pass statement)
```

#### Step 8: Calculate Total
✅ **Status:** Required
```
total = subtotal - discount + delivery_fee
order.total_price = total
```

#### Step 9: Create or Reset Payment
✅ **Status:** Required
- Creates Payment record with amount = order.total_price
- Sets status to PENDING
- Generates unique reference

#### Step 10: Initialize Paystack Payment
✅ **Status:** Required
- Sends payment.amount to Paystack
- Gets authorization_url from Paystack
- Returns URL to frontend

#### Step 11: Notify Vendors
✅ **Status:** Optional (try-catch)
- Creates Notification for each vendor

#### Step 12: Clear Cart
✅ **Status:** Required
- Deletes CartItems

#### Final Response
```json
{
    "success": true,
    "data": {
        "order_id": "uuid-string",
        "authorization_url": "https://checkout.paystack.com/...",
        "reference": "order-id-random",
        "amount": 15000.00,
        "delivery_fee": 2500.00 OR 0
    },
    "message": "Checkout initialized successfully"
}
```

---

### B. Installment Checkout (`POST /api/transactions/checkout/installment/`)

**Same validation flow as Single Payment Checkout:**

✅ **Status:** REQUIRED
1. Cart checks (exists and has items)
2. Customer profile validation
3. **Shipping coordinates (CONDITIONAL based on ENFORCE_DELIVERY_FEE_ON_CHECKOUT)**
4. Order creation and item conversion
5. Delivery coordinate retrieval (optional, wrapped in try-catch)
6. Delivery fee calculation (optional, only if coordinates available)

**Additional steps for Installment:**
7. Validate installment duration from request body
8. Create InstallmentPlan
9. Generate individual InstallmentPayment records
10. Initialize payment for FIRST installment only
11. Notify vendors
12. Clear cart

---

## Test Scenarios

### Scenario 1: Complete Data (Happy Path)
**Configuration:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False`

**Setup:**
- User has customer_profile with shipping_latitude and shipping_longitude
- Vendor has store_latitude and store_longitude
- Cart has valid items

**Expected Result:**
```
✅ Checkout succeeds
✅ Delivery fee calculated
✅ Order created with delivery_fee > 0
✅ Payment initialized with full amount (including delivery fee)
```

**Response:**
```json
{
    "delivery_fee": 2500.00,
    "amount": 18500.00
}
```

---

### Scenario 2: Missing Customer Coordinates (Enforcement OFF)
**Configuration:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False`

**Setup:**
- User has customer_profile but NO shipping coordinates
- Vendor has store coordinates
- Cart has valid items

**Expected Result:**
```
✅ Checkout succeeds (OVERRIDE by setting)
✅ Delivery fee NOT calculated (missing customer coords)
✅ Order created with delivery_fee = 0 (default)
✅ Payment initialized with subtotal only (no delivery fee)
✅ Log: "Delivery fee enforcement disabled: Allowing checkout without coordinates"
```

**Response:**
```json
{
    "delivery_fee": 0,
    "amount": 16000.00
}
```

---

### Scenario 3: Missing Customer Coordinates (Enforcement ON)
**Configuration:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=True`

**Setup:**
- User has customer_profile but NO shipping coordinates
- Cart has valid items

**Expected Result:**
```
❌ Checkout FAILS
❌ Error: "Shipping address with coordinates is required..."
HTTP Status: 400 BAD_REQUEST
```

**Response:**
```json
{
    "success": false,
    "error": "Shipping address with coordinates is required. Please update your profile..."
}
```

---

### Scenario 4: Missing Vendor Coordinates
**Configuration:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False`

**Setup:**
- User has customer_profile with coordinates
- Vendor has NO store coordinates
- Cart has valid items

**Expected Result:**
```
✅ Checkout succeeds
✅ Delivery fee NOT calculated (missing vendor coords)
✅ Order created with delivery_fee = 0
✅ Payment initialized with subtotal only
✅ Log: "Incomplete coordinates for order..."
```

**Response:**
```json
{
    "delivery_fee": 0,
    "amount": 16000.00
}
```

---

### Scenario 5: Delivery Fee Calculation Fails
**Configuration:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False`

**Setup:**
- User has customer_profile with coordinates
- Vendor has store coordinates
- Radar API fails or times out

**Expected Result:**
```
✅ Checkout succeeds (delivery fee failure is not blocking)
✅ Order created with delivery_fee = 0 (calculation failed)
✅ Payment initialized with subtotal only
✅ Log: "Delivery fee calculation failed: [error message]"
```

**Response:**
```json
{
    "delivery_fee": 0,
    "amount": 16000.00
}
```

---

### Scenario 6: Delivery Address Outside Radius
**Configuration:** `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False`

**Setup:**
- Both coordinates present
- Distance > DELIVERY_MAX_DISTANCE_MILES (e.g., > 20 miles)

**Expected Result:**
```
✅ Checkout succeeds (no hard block on delivery distance)
✅ Delivery fee NOT calculated (outside radius)
✅ Order created with delivery_fee = 0
✅ Log: "Delivery address is outside our [X] mile radius"
```

**Response:**
```json
{
    "delivery_fee": 0,
    "amount": 16000.00
}
```

**Note:** Frontend should warn user about delivery radius

---

## Testing Commands

### Test Scenario 1 (Happy Path)
```bash
curl -X POST http://localhost:8000/api/transactions/checkout/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Check Current Setting
```python
from django.conf import settings
print(settings.ENFORCE_DELIVERY_FEE_ON_CHECKOUT)  # False
```

### Toggle Setting at Runtime (for testing)
```python
from django.conf import settings

# Check current value
current = settings.ENFORCE_DELIVERY_FEE_ON_CHECKOUT

# Override for testing (not persistent)
settings.ENFORCE_DELIVERY_FEE_ON_CHECKOUT = True

# Toggle back
settings.ENFORCE_DELIVERY_FEE_ON_CHECKOUT = current
```

---

## Implementation Summary

### Files Modified

1. **`e_commerce_api/settings.py`**
   - Added `ENFORCE_DELIVERY_FEE_ON_CHECKOUT` setting

2. **`transactions/views.py`** (CheckoutView)
   - Modified shipping coordinate validation to check `ENFORCE_DELIVERY_FEE_ON_CHECKOUT`
   - If False: logs info and continues
   - If True: returns error and blocks checkout

3. **`transactions/views.py`** (InstallmentCheckoutView)
   - Applied same conditional validation as CheckoutView

### Key Behaviors

✅ **Checkout always processes if:**
- Cart exists and has items
- User has customer_profile
- `ENFORCE_DELIVERY_FEE_ON_CHECKOUT` is False

✅ **Delivery fee is OPTIONAL:**
- If coordinates missing: delivery_fee = 0
- If calculation fails: delivery_fee = 0
- Order still completes successfully

✅ **Delivery fee is CALCULATED if:**
- Both customer and vendor coordinates are available
- Radar API returns successfully
- Distance is within configured radius

---

## Environment Variable Guide

### Default State
```env
# .env file (not set, uses default)
# ENFORCE_DELIVERY_FEE_ON_CHECKOUT is not defined
```

Result: Uses default `False` from settings.py

### To Enforce Delivery Fees (Strict Mode)
```env
ENFORCE_DELIVERY_FEE_ON_CHECKOUT=True
```

Result: Checkout blocks if coordinates missing

### To Allow Checkout Without Delivery (Lenient Mode)
```env
ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False
```

Result: Checkout succeeds even without coordinates

---

## Troubleshooting

### Issue: Checkout blocked despite setting False
**Cause:** Environment variable not loaded
**Solution:** 
```bash
# Verify .env file has the setting
grep ENFORCE_DELIVERY_FEE_ON_CHECKOUT .env

# Restart Django server
python manage.py runserver
```

### Issue: Delivery fee always 0
**Cause:** Missing coordinates
**Solution:**
```bash
# Check customer profile
python manage.py shell
>>> from authentication.models import CustomUser
>>> user = CustomUser.objects.get(email='test@example.com')
>>> print(user.customer_profile.shipping_latitude)
>>> print(user.customer_profile.shipping_longitude)

# Check vendor profile
>>> from users.models import Vendor
>>> vendor = Vendor.objects.first()
>>> print(vendor.store_latitude)
>>> print(vendor.store_longitude)
```

### Issue: Delivery fee calculated but not showing in response
**Cause:** Serializer not including field
**Solution:** Check OrderSerializer includes `delivery_fee` in `fields`

---

## Summary

✅ **Delivery fee toggle implemented successfully**

The system now allows:
1. **Flexible checkout**: When `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=False` (default)
2. **Strict checkout**: When `ENFORCE_DELIVERY_FEE_ON_CHECKOUT=True`
3. **Graceful fallbacks**: Missing coordinates/API failures don't block checkout
4. **Optional fee calculation**: Fee is calculated only when all data is available

The implementation follows Django best practices with atomic transactions and comprehensive error handling.
