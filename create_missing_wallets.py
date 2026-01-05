#!/usr/bin/env python
"""
Management command to create missing wallets for existing users.
Run this command if you had users before the wallet signal was added.

Usage: python manage.py shell < create_missing_wallets.py
Or from Django shell: python manage.py shell
Then: exec(open('create_missing_wallets.py').read())
"""

from authentication.models import CustomUser
from transactions.models import Wallet

def create_missing_wallets():
    """Create wallets for all users who don't have one."""
    users_without_wallet = CustomUser.objects.exclude(wallet__isnull=False)
    
    count = 0
    for user in users_without_wallet:
        wallet, created = Wallet.objects.get_or_create(user=user)
        if created:
            count += 1
            print(f"✓ Created wallet for {user.email}")
    
    print(f"\n✓ Total wallets created: {count}")
    print(f"✓ All users now have wallets!")

if __name__ == "__main__":
    create_missing_wallets()
