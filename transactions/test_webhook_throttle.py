"""
Paystack's webhook calls come from three fixed IPs, so the global anonymous throttle
(100 requests an hour per IP) would start answering 429 once live traffic passed a few hundred
events an hour. The webhooks are authenticated by their HMAC signature, not by a rate limit.

A forged signature is rejected with 403, so a flood of them is a clean probe: 403 every time
means the throttle is out of the way, and a 429 would mean it is still in force.
"""

from django.core.cache import cache
from django.test import TestCase, override_settings

SECRET = 'sk_test_dummy_secret'
BODY = b'{"id": 1, "event": "charge.success", "data": {"reference": "ORD-x"}}'
# The global limit is 100 an hour; go clearly past it.
REQUESTS = 120


@override_settings(PAYSTACK_SECRET_KEY=SECRET)
class WebhookThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def _flood(self, url):
        return [
            self.client.post(
                url, data=BODY, content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE='forged',
            ).status_code
            for _ in range(REQUESTS)
        ]

    def test_main_webhook_is_never_throttled(self):
        self.assertEqual(set(self._flood('/transactions/webhook/')), {403})

    def test_installment_webhook_is_never_throttled(self):
        self.assertEqual(set(self._flood('/transactions/installment-webhook/')), {403})

    def test_a_forged_event_is_still_rejected_not_accepted(self):
        # Removing the throttle must not have loosened authentication.
        response = self.client.post(
            '/transactions/webhook/', data=BODY, content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='forged',
        )
        self.assertEqual(response.status_code, 403)

    def test_the_global_throttle_does_apply_to_an_ordinary_anonymous_endpoint(self):
        # Control: without this, the tests above could pass simply because throttling is off
        # in the test settings.
        codes = {self.client.get('/store/products/').status_code for _ in range(REQUESTS)}
        self.assertIn(429, codes)
