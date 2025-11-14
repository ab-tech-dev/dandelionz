import requests
from django.conf import settings

class Paystack:
    base_url = getattr(settings, "PAYSTACK_BASE_URL", "https://api.paystack.co")
    secret_key = settings.PAYSTACK_SECRET_KEY

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def initialize_payment(self, email, amount, reference, callback_url):
        payload = {
            "email": email,
            "amount": int(amount * 100),   # kobo
            "reference": reference,
            "callback_url": callback_url,
        }
        resp = requests.post(f"{self.base_url}/transaction/initialize",
                             json=payload, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def verify_payment(self, reference):
        resp = requests.get(f"{self.base_url}/transaction/verify/{reference}",
                            headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
