# SMTP Email Sending Issues - Solutions Implemented

## Problem Summary
Your Celery email tasks were failing with two main errors:
1. `SMTPServerDisconnected: Connection unexpectedly closed` - SMTP connection drops during message sending
2. `socket.gaierror: [Errno -5] No address associated with hostname` - DNS resolution failures

These are common issues in containerized environments due to:
- SMTP connection timeouts
- DNS resolution issues in Docker
- No connection pooling/reuse
- Insufficient retry logic with proper backoff

## Solutions Implemented

### 1. **Custom Robust SMTP Email Backend** (`authentication/core/email_backend.py`)
A new custom email backend with:
- **Connection pooling**: Reuses SMTP connections when possible
- **Automatic retry logic**: Retries up to 3 times with exponential backoff when connection fails
- **Timeout handling**: 30-second timeout for all SMTP operations
- **Better error handling**: Distinguishes between different error types (connection, network, SMTP)
- **Proper connection cleanup**: Handles `SMTPServerDisconnected` gracefully on close

### 2. **Enhanced Email Configuration** (`e_commerce_api/settings.py`)
```python
EMAIL_BACKEND = 'authentication.core.email_backend.RobustSMTPEmailBackend'
EMAIL_TIMEOUT = 30  # 30 seconds timeout
EMAIL_CONNECTION_RETRY_ATTEMPTS = 3  # Retry 3 times on connection failure
EMAIL_CONNECTION_RETRY_DELAY = 2  # 2 seconds between retries
```

### 3. **Improved Celery Task Configuration** (`authentication/verification/tasks.py`)
Updated both email tasks with better retry strategies:
- **Max retries**: Increased from 3 to 5 attempts
- **Initial delay**: Added 60-second initial delay before first retry
- **Exponential backoff**: Backoff increases up to 5 minutes between retries
- **Jitter**: Random jitter added to prevent thundering herd

### 4. **Enhanced Email Service** (`authentication/verification/emails.py`)
- Added per-attempt logging with attempt numbers
- Better error messages differentiating between transient and permanent failures

## Key Improvements

### Connection Resilience
- Automatic reconnection on SMTP errors
- Configurable timeouts prevent hanging connections
- Network error detection and recovery

### Retry Strategy
```
Attempt 1: Immediate (0s)
Attempt 2: After 60s
Attempt 3: After 120s (with jitter)
Attempt 4: After 240s (with jitter)
Attempt 5: After 300s (with jitter)
```

### Error Handling
- `SMTPConnectionError`: Triggers retry with delay
- `SMTPServerDisconnected`: Closes connection, triggers reconnect
- `OSError` (network): Triggers retry with delay
- `SMTPException`: Logged, triggers retry

## Testing the Fix

### Test 1: Verify Configuration
```bash
python manage.py shell
from django.core.mail import get_connection
conn = get_connection()
print(type(conn).__name__)  # Should print: RobustSMTPEmailBackend
```

### Test 2: Send Test Email
```bash
python manage.py shell
from django.core.mail import send_mail
send_mail(
    'Test Subject',
    'Test message',
    'from@example.com',
    ['to@example.com'],
)
```

### Test 3: Monitor Celery Logs
```bash
docker logs celery-1 -f
```
Look for: `SMTP connection established successfully` and improved retry messages

## Environment Variables Checklist

Ensure these are set in your `.env`:
- `EMAIL_HOST` - SMTP server hostname
- `EMAIL_PORT` - SMTP port (usually 587 for TLS or 465 for SSL)
- `EMAIL_USE_TLS` - True for TLS (port 587)
- `EMAIL_USE_SSL` - True for SSL (port 465)
- `EMAIL_HOST_USER` - SMTP username
- `EMAIL_HOST_PASSWORD` - SMTP password
- `DEFAULT_FROM_EMAIL` - From address for emails

## Monitoring & Debugging

### Check Backend is Loaded
Monitor Celery logs for:
```
SMTP connection established successfully on attempt 1
```

### Connection Retry Logs
```
SMTP connection error on attempt 1/3: [error details]
SMTP connection established successfully on attempt 2
```

### Task Success Indicator
Look for completion message:
```
Task authentication.verification.send_verification_email[xxx] succeeded in Xs: {'status': 'success', ...}
```

## Additional Recommendations

1. **Docker DNS Issues**
   - If you see DNS errors, verify Docker network configuration
   - Ensure `nameserver` is set correctly in Docker containers

2. **SMTP Server Health**
   - Monitor your SMTP server uptime
   - Consider using a transactional email service (SendGrid, AWS SES, etc.)

3. **Rate Limiting**
   - Some SMTP servers limit concurrent connections
   - The custom backend respects these limits

4. **SSL/TLS Configuration**
   - Test locally: `openssl s_client -connect mail.example.com:587 -starttls smtp`
   - Verify certificates are valid

5. **Production Optimization**
   ```python
   # Consider adding in settings for production:
   EMAIL_POOL_SIZE = 10  # Connection pool size
   EMAIL_POOL_TIMEOUT = 60  # Pool timeout in seconds
   ```

## Files Modified

1. `e_commerce_api/settings.py` - Email configuration
2. `authentication/core/email_backend.py` - NEW: Custom SMTP backend
3. `authentication/verification/emails.py` - Enhanced error logging
4. `authentication/verification/tasks.py` - Improved retry strategy

## Rollback Instructions

If you need to revert to standard Django SMTP backend:
```python
# In settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
```

And update Celery task retry settings back to:
```python
retry_kwargs={'max_retries': 3}
```
