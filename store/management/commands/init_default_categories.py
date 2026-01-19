"""
Management command to initialize default product categories.
Run with: python manage.py init_default_categories

This creates the default category list without requiring migrations.
"""
from django.core.management.base import BaseCommand
from store.models import Category


class Command(BaseCommand):
    help = 'Initialize default product categories'

    def handle(self, *args, **options):
        DEFAULT_CATEGORIES = [
            ('electronics', 'Electronics'),
            ('fashion', 'Fashion'),
            ('home_appliances', 'Home Appliances'),
            ('beauty', 'Beauty & Personal Care'),
            ('sports', 'Sports & Outdoors'),
            ('automotive', 'Automotive'),
            ('books', 'Books'),
            ('toys', 'Toys & Games'),
            ('groceries', 'Groceries'),
            ('computers', 'Computers & Accessories'),
            ('phones', 'Phones & Tablets'),
            ('jewelry', 'Jewelry & Watches'),
            ('baby', 'Baby Products'),
            ('pets', 'Pet Supplies'),
            ('office', 'Office Products'),
            ('gaming', 'Video Games & Consoles'),
        ]

        created_count = 0
        existing_count = 0

        for slug, name in DEFAULT_CATEGORIES:
            category, created = Category.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created category: {name}')
                )
            else:
                existing_count += 1
                self.stdout.write(
                    self.style.WARNING(f'✓ Category already exists: {name}')
                )

        total = created_count + existing_count
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Done! Created: {created_count}, Already existed: {existing_count}, Total: {total}'
            )
        )
