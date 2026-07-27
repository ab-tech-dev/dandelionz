from decimal import Decimal

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_secret_key():
    """
    Return the Paystack secret key, or fail with a message that says what is wrong.

    Previously the key was read into a class attribute at import time. When it was unset
    the failure surfaced as `AttributeError: 'NoneType' object has no attribute 'encode'`
    from inside webhook signature verification - which reads like a bug in the webhook
    rather than missing configuration.
    """
    key = getattr(settings, "PAYSTACK_SECRET_KEY", None)
    if not key:
        raise ImproperlyConfigured(
            "PAYSTACK_SECRET_KEY is not set. Payment initialisation, transfers, and "
            "webhook signature verification cannot work without it. Set it in the "
            "environment on the server."
        )
    return key


class Paystack:
    base_url = getattr(settings, "PAYSTACK_BASE_URL", "https://api.paystack.co")

    def __init__(self):
        # Resolved per-instance rather than at import time so a missing key raises where
        # it is used, with a message that explains itself.
        self.secret_key = get_secret_key()
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

    def resolve_account(self, account_number, bank_code):
        """Verify bank account number and return account name."""
        params = {
            "account_number": account_number,
            "bank_code": bank_code,
        }
        resp = requests.get(f"{self.base_url}/bank/resolve",
                            params=params, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def create_transfer_recipient(self, name, account_number, bank_code, currency="NGN"):
        """Register a transfer recipient on Paystack."""
        payload = {
            "type": "nuban",
            "name": name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": currency,
        }
        resp = requests.post(f"{self.base_url}/transferrecipient",
                             json=payload, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def initiate_transfer(self, amount, recipient_code, reference, reason=""):
        """Initiate a transfer to a recipient."""
        payload = {
            "source": "balance",
            "amount": int(amount * 100),  # kobo
            "recipient": recipient_code,
            "reference": reference,
            "reason": reason,
        }
        resp = requests.post(f"{self.base_url}/transfer",
                             json=payload, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def refund(self, transaction, amount=None, merchant_note="", customer_note=""):
        """
        Refund a charge back to the card it came from.

        ``transaction`` is Paystack's own transaction id or reference - this is why
        WalletDeposit captures paystack_transaction_id at verification time. Refunds are
        the only way to return deposited funds: deposits land in the spendable bucket and
        must never be payable to a bank account, so a transfer is not an option.

        ``amount`` is in naira and converted to kobo here, matching the other methods.
        Omitting it refunds the full transaction, which is Paystack's default.

        Paystack accepts the refund and settles it asynchronously; the outcome arrives as a
        refund.processed or refund.failed webhook.
        """
        payload = {"transaction": str(transaction)}
        if amount is not None:
            payload["amount"] = int(Decimal(str(amount)) * 100)  # kobo
        if merchant_note:
            payload["merchant_note"] = merchant_note
        if customer_note:
            payload["customer_note"] = customer_note

        resp = requests.post(f"{self.base_url}/refund",
                             json=payload, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def list_banks(self):
        """Fetch list of banks from Paystack."""
        resp = requests.get(f"{self.base_url}/bank",
                            headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
