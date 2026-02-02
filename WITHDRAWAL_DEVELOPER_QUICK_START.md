# Withdrawal System - Developer Quick Start

**Time to understand:** 5 minutes  
**Time to implement:** Already done! ✅

---

## 🚀 Quick Start for Developers

### The Main Concept
Users can withdraw money from their wallet. Admins must approve before funds transfer.

### Three Key Files

#### 1. Service Layer: `users/services/payout_service.py`
```python
# All withdrawal logic is here
from users.services.payout_service import PayoutService

# Validate withdrawal
is_valid, error_msg = PayoutService.validate_withdrawal_request(user, amount)

# Verify PIN
pin_valid, error = PayoutService.verify_pin(user, pin)

# Create withdrawal (handles everything: debit, notify admin, etc.)
payout, error = PayoutService.create_withdrawal_request(
    user=user,
    amount=amount,
    bank_name='GTBank',
    account_number='0123456789',
    account_name='John Doe',
    vendor=None  # None for customers, vendor obj for vendors
)
```

#### 2. Views: `users/views.py`
```python
# Vendor withdrawal endpoint
POST /api/vendor/wallet/request-withdrawal/
{
    "amount": 50000.00,
    "pin": "1234"
}

# Admin approval endpoint
POST /api/admin/finance/approve-withdrawal/
{
    "withdrawal_id": "uuid",
    "notes": "Approved"
}

# Admin rejection endpoint
POST /api/admin/finance/reject-withdrawal/
{
    "withdrawal_id": "uuid",
    "reason": "Account verification failed"
}
```

#### 3. Models: `users/models.py`
```python
# PayoutRequest - tracks all withdrawals
class PayoutRequest(models.Model):
    vendor = ForeignKey(Vendor)  # NULL for customers
    user = ForeignKey(User)  # NULL for vendors
    amount = DecimalField
    status = CharField  # pending|processing|successful|failed|cancelled
    reference = CharField  # WTH-XXXXXXXXXX (unique)
    created_at = DateTimeField
    processed_at = DateTimeField  # NULL until approved
    failure_reason = TextField  # NULL unless rejected

# PaymentPIN - PIN for withdrawal authorization
class PaymentPIN(models.Model):
    user = OneToOneField(User)
    pin_hash = CharField  # PBKDF2 hashed, never plain text
    is_default = BooleanField  # True if still using 0000
```

---

## 🔄 Flow in 60 Seconds

```
User submits withdrawal
    ↓
System validates PIN & balance
    ↓
Wallet debited immediately
    ↓
PayoutRequest created (status: pending)
    ↓
Admins notified (email + WebSocket)
    ↓
Admin reviews & approves
    ↓
Status → processing
    ↓
User notified: "Approved"
    ↓
(Payment provider transfers money)
    ↓
Status → successful
```

---

## 🧪 Running Tests

```bash
# Run all withdrawal tests
python manage.py test users.tests.test_withdrawal_flow -v 2

# Run specific test
python manage.py test users.tests.test_withdrawal_flow.WithdrawalValidationTests.test_validate_withdrawal_with_sufficient_balance -v 2
```

---

## 🐛 Debugging Tips

### "Admin not notified"
→ Check: Email backend configured? Celery running? Admin email valid?

### "Withdrawal stuck in pending"
→ Check: PayoutRequest status in database. Is it still 'pending'? Can admin approve?

### "PIN error despite correct PIN"
→ Check: PIN was hashed correctly with make_password(). is_default=False?

### "Wallet shows wrong balance"
→ Check: WalletTransaction log. All debits/credits recorded?

---

## 📋 Common Tasks

### Task 1: Add a New Validation
```python
# In PayoutService.validate_withdrawal_request()
# Add your check:
if some_new_condition_fails:
    return False, "Your error message"
```

### Task 2: Change Notification Priority
```python
# In PayoutService.notify_admins_of_withdrawal()
# Change priority calculation:
priority='high' if payout.amount > Decimal('200000') else 'normal'
```

### Task 3: Add New Admin Endpoint
```python
# In AdminFinanceViewSet in views.py
@action(detail=False, methods=["post"])
def new_endpoint(self, request):
    admin = self.get_admin(request)
    if not admin:
        return Response({"message": "Access denied"}, status=403)
    
    # Your code here
    return Response({"success": True})
```

---

## 🔐 Security Reminders

✅ **DO:**
- Always use PayoutService for withdrawals
- Verify PIN with PayoutService.verify_pin()
- Use @transaction.atomic for wallet operations
- Log important events
- Return clear error messages

❌ **DON'T:**
- Store PIN in plain text
- Allow negative wallet balance
- Skip PIN verification
- Log sensitive data (account numbers)
- Allow duplicate simultaneous withdrawals

---

## 📚 Documentation Files

| File | Purpose | Read Time |
|------|---------|-----------|
| WITHDRAWAL_QUICK_REFERENCE.md | Endpoint lookup, quick flows | 10 min |
| WITHDRAWAL_FLOW_DOCUMENTATION.md | Complete technical reference | 30 min |
| WITHDRAWAL_DIAGRAMS.md | Visual flows and architecture | 15 min |
| WITHDRAWAL_IMPLEMENTATION_SUMMARY.md | What changed and why | 20 min |
| WITHDRAWAL_CHECKLIST.md | Validation and deployment checklists | As needed |

---

## 🎯 For Code Reviews

**Check these when reviewing withdrawal code:**

1. **Validation**
   - [ ] Decimal type used (not float)
   - [ ] PIN hashed (not plain text)
   - [ ] Balance checked before debit
   - [ ] Amount > 0 validated

2. **Transactions**
   - [ ] @transaction.atomic used
   - [ ] All or nothing logic
   - [ ] No orphaned records possible

3. **Notifications**
   - [ ] Admin notified
   - [ ] User notified of approval/rejection
   - [ ] Async (no blocking)

4. **Security**
   - [ ] Permission checks
   - [ ] Audit trail
   - [ ] Error handling
   - [ ] No data leaks

5. **Testing**
   - [ ] Happy path tested
   - [ ] Error cases tested
   - [ ] Edge cases tested

---

## 🚨 Emergency Procedures

### If withdrawal system is broken:

1. **Disable withdrawals temporarily**
   ```python
   # In view:
   return Response({"message": "Withdrawals temporarily disabled for maintenance"}, status=503)
   ```

2. **Refund stuck withdrawals**
   ```python
   # In Django shell:
   for payout in PayoutRequest.objects.filter(status='processing'):
       wallet = payout.vendor.user.wallet if payout.vendor else payout.user.wallet
       wallet.credit(payout.amount, f'Emergency refund {payout.reference}')
   ```

3. **Check logs**
   ```bash
   tail -f django.log | grep withdrawal
   tail -f celery.log | grep notification
   ```

4. **Escalate if needed**
   → Contact: [Your team's on-call]

---

## 💡 Tips & Tricks

### Tip 1: Testing a withdrawal locally
```python
# In Django shell:
from users.models import Vendor, PaymentPIN
from users.services.payout_service import PayoutService
from decimal import Decimal

user = User.objects.get(email='vendor@test.com')
vendor = user.vendor_profile

# Set PIN if not done
pin_obj, _ = PaymentPIN.objects.get_or_create(user=user)
pin_obj.set_pin('1234')

# Test withdrawal
payout, error = PayoutService.create_withdrawal_request(
    user=user,
    amount=Decimal('1000.00'),
    bank_name='GTBank',
    account_number='0123456789',
    account_name='Test',
    vendor=vendor
)
print(f"Created: {payout.reference if payout else error}")
```

### Tip 2: Quick admin approval
```python
# In Django shell:
from users.models import PayoutRequest

payout = PayoutRequest.objects.get(reference='WTH-ABC123')
payout.status = 'processing'
payout.save()
print(f"Approved: {payout.reference}")
```

### Tip 3: Monitor withdrawals
```bash
# Watch for new withdrawals
python manage.py shell < - << EOF
from users.models import PayoutRequest
from django.utils import timezone
from datetime import timedelta

recent = PayoutRequest.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=1)
).order_by('-created_at')

for p in recent:
    print(f"{p.reference}: {p.status} - ₦{p.amount}")
EOF
```

---

## ✅ Pre-Deployment Checklist

- [ ] Read WITHDRAWAL_QUICK_REFERENCE.md
- [ ] Run all tests: `pytest users/tests/test_withdrawal_flow.py`
- [ ] Test withdrawal flow in staging
- [ ] Test approval/rejection workflow
- [ ] Verify admin receives notifications
- [ ] Check email delivery
- [ ] Verify WebSocket notifications
- [ ] Test wallet refund on rejection
- [ ] Check audit trail (reference numbers in logs)
- [ ] Review error messages
- [ ] Monitor performance (< 2 sec response)

---

## 📞 Getting Help

### If you're stuck:
1. Check the relevant documentation file
2. Search the test file for examples
3. Check WITHDRAWAL_TROUBLESHOOTING (error messages)
4. Review the model definitions
5. Check the service implementation

### Common questions:
**Q: How do I add a new withdrawal validation?**  
A: Edit `PayoutService.validate_withdrawal_request()`

**Q: How do I change the notification message?**  
A: Edit `PayoutService.notify_admins_of_withdrawal()`

**Q: How do I test a withdrawal?**  
A: Use test_withdrawal_flow.py as reference

**Q: How do I debug a failed withdrawal?**  
A: Check django.log, celery.log, and database

---

## 🎉 You're Ready!

The withdrawal system is production-ready and fully documented.

**Next Step:** Deploy with confidence! 🚀

---

*Questions? See the comprehensive documentation files.*
