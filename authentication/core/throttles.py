from rest_framework.throttling import SimpleRateThrottle, AnonRateThrottle
from django.core.cache import cache
from authentication.core.ip_utils import get_client_ip
import logging

logger = logging.getLogger(__name__)


class StrongIPBasedThrottle(SimpleRateThrottle):
    """
    Custom throttle that enforces strict rate limiting per IP address
    and blocks IPs after excessive requests to prevent DDoS attacks.
    
    Very aggressive throttling suitable for security-sensitive endpoints
    like email verification sending.
    """
    scope = 'strong_ip_based'
    
    def get_cache_key(self):
        """Generate cache key based on IP address"""
        if self.request is None:
            return None
        
        # Get client IP from request metadata
        ip = get_client_ip(self.request.META)
        
        # Check if IP is already blocked
        if cache.get(f"ip_blocked:{ip}"):
            logger.warning(f"Blocked request from IP marked for DDoS protection: {ip}")
            return None  # This will cause throttling to fail
        
        return f"throttle_{self.scope}_{ip}"
    
    def throttle_success(self):
        """
        Allow the request and track it.
        Returns True if request is allowed.
        """
        if self.request is None:
            return True
        
        if self.key is None:
            return True
        
        self.history = cache.get(self.key, [])
        self.now = self.timer()
        
        # Drop any requests from the history which have now passed the
        # throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        
        if len(self.history) >= self.num_requests:
            # IP has exceeded rate limit
            ip = get_client_ip(self.request.META)
            failed_attempts = cache.get(f"verification_email_attempts:{ip}", 0) + 1
            cache.set(f"verification_email_attempts:{ip}", failed_attempts, timeout=3600)  # 1 hour window
            
            # Block IP after 15 attempts in 1 hour (suspected DDoS)
            if failed_attempts >= 15:
                cache.set(f"ip_blocked:{ip}", True, timeout=86400)  # Block for 24 hours
                logger.error(f"IP {ip} blocked for DDoS protection. Attempts: {failed_attempts}")
            
            return False
        
        self.history.insert(0, self.now)
        cache.set(self.key, self.history, self.duration)
        return True


class EmailVerificationThrottle(StrongIPBasedThrottle):
    """
    Very strong throttle for email verification endpoint.
    Limits to 5 requests per hour per IP to prevent abuse.
    """
    scope = 'email_verification'
    THROTTLE_RATES = {
        'email_verification': '5/hour',
    }
    
    def parse_rate(self, rate):
        """
        Given the request rate string, return a two tuple of:
        <allowed number of requests>, <period of time in seconds>
        """
        num, period = rate.split('/')
        num_requests = int(num)
        duration = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period[0]]
        return (num_requests, duration)
    
    def __init__(self):
        super().__init__()
        # Override with strong throttle rates
        rate = self.THROTTLE_RATES.get(self.scope, '5/hour')
        self.num_requests, self.duration = self.parse_rate(rate)
