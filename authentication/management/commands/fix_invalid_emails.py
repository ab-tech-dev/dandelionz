"""
Management command to identify and fix invalid email addresses in the database.
Usage: python manage.py fix_invalid_emails
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import re
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


class Command(BaseCommand):
    help = 'Find and report invalid email addresses in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix invalid emails by appending a domain',
        )
        parser.add_argument(
            '--domain',
            type=str,
            default='placeholder.local',
            help='Domain to append to invalid emails when fixing (default: placeholder.local)',
        )

    def is_valid_email(self, email):
        """Validate email format"""
        if not email or not isinstance(email, str):
            return False
        
        email = email.strip()
        
        # Check basic format
        if not EMAIL_REGEX.match(email):
            return False
        
        # Ensure it has both local and domain parts
        if '@' not in email:
            return False
        
        local_part, domain = email.rsplit('@', 1)
        
        # Local part should not be empty
        if not local_part:
            return False
        
        # Domain should have at least one dot
        if '.' not in domain:
            return False
        
        # Domain parts should not be empty
        parts = domain.split('.')
        if any(not part for part in parts):
            return False
        
        return True

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Scanning for invalid email addresses...'))
        
        all_users = User.objects.all()
        invalid_users = []
        
        for user in all_users:
            if not self.is_valid_email(user.email):
                invalid_users.append(user)
        
        if not invalid_users:
            self.stdout.write(self.style.SUCCESS('✓ No invalid emails found!'))
            return
        
        self.stdout.write(self.style.WARNING(f'\n⚠ Found {len(invalid_users)} user(s) with invalid emails:\n'))
        
        for user in invalid_users:
            self.stdout.write(f'  UUID: {user.uuid}')
            self.stdout.write(f'  Email: "{user.email}"')
            self.stdout.write(f'  Full Name: {user.full_name}')
            self.stdout.write(f'  Created: {user.created_at}')
            self.stdout.write('')
        
        if options['fix']:
            self.stdout.write(self.style.WARNING(f'\nFixing {len(invalid_users)} invalid emails...'))
            domain = options['domain']
            
            for user in invalid_users:
                old_email = user.email
                # Append domain to emails that don't have one
                if '@' not in user.email:
                    user.email = f"{user.email}@{domain}"
                # Fix emails where domain is incomplete (no dot)
                elif '.' not in user.email.split('@')[1]:
                    local, incomplete_domain = user.email.rsplit('@', 1)
                    user.email = f"{local}@{incomplete_domain}.{domain}"
                
                try:
                    user.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Fixed: "{old_email}" → "{user.email}"')
                    )
                    logger.info(f'Fixed invalid email for user {user.uuid}: {old_email} → {user.email}')
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error fixing "{old_email}": {str(e)}')
                    )
                    logger.error(f'Error fixing email for user {user.uuid}: {str(e)}')
            
            self.stdout.write(self.style.SUCCESS('\n✓ Email fixing complete!'))
        else:
            self.stdout.write(
                self.style.WARNING('\nTo fix these emails, run: python manage.py fix_invalid_emails --fix')
            )
