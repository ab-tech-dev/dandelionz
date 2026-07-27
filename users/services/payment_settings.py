"""
Writing payout bank details onto a profile.

Shared by vendors, admins, and customers - all three store the same five fields
(bank_name, bank_code, account_number, account_name, recipient_code) and all three
previously had subtly different update code paths.

Two things this centralises:

1. **bank_code is persisted.** It was silently dropped before: the update serializer had no
   such field, so DRF discarded it and no view ever assigned it. Since
   PayoutService.get_or_create_paystack_recipient returns None when bank_code is blank, no
   transfer recipient could ever be created and every withdrawal failed at
   "No transfer recipient code available".

2. **A changed destination clears the cached recipient_code.** recipient_code is a Paystack
   handle pointing at one specific account. Keeping it after the user edits their bank
   details would send the next payout to the *old* account.
"""

import logging

logger = logging.getLogger(__name__)

BANK_FIELDS = ('bank_name', 'bank_code', 'account_number', 'account_name')

# Changing either of these means the money would land somewhere different.
DESTINATION_FIELDS = ('bank_code', 'account_number')


def apply_payment_settings(profile, data):
    """
    Apply validated bank detail fields to a payout profile and save it.

    `profile` is a Vendor, AdminPayoutProfile, or Customer - anything carrying the five
    payout fields. Returns the saved profile.
    """
    destination_changed = False

    for field in BANK_FIELDS:
        if field not in data:
            continue
        new_value = data[field]
        if field in DESTINATION_FIELDS and (getattr(profile, field) or '') != (new_value or ''):
            destination_changed = True
        setattr(profile, field, new_value)

    if destination_changed and profile.recipient_code:
        logger.info(
            f"Payout destination changed for {profile}; clearing cached recipient_code "
            f"so a new Paystack recipient is created for the new account."
        )
        profile.recipient_code = ''

    profile.save()
    return profile
