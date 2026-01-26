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
            {
                'slug': 'electronics',
                'name': 'Electronics',
                'description': 'Electronic devices, gadgets, and accessories'
            },
            {
                'slug': 'fashion',
                'name': 'Fashion',
                'description': 'Clothing, shoes, and fashion accessories'
            },
            {
                'slug': 'home_appliances',
                'name': 'Home Appliances',
                'description': 'Kitchen and home appliances for modern living'
            },
            {
                'slug': 'beauty',
                'name': 'Beauty & Personal Care',
                'description': 'Cosmetics, skincare, and personal care products'
            },
            {
                'slug': 'sports',
                'name': 'Sports & Outdoors',
                'description': 'Sports equipment and outdoor gear'
            },
            {
                'slug': 'automotive',
                'name': 'Automotive',
                'description': 'Car accessories and automotive products'
            },
            {
                'slug': 'books',
                'name': 'Books',
                'description': 'Books, e-books, and educational materials'
            },
            {
                'slug': 'toys',
                'name': 'Toys & Games',
                'description': 'Toys, games, and entertainment products'
            },
            {
                'slug': 'groceries',
                'name': 'Groceries',
                'description': 'Food, beverages, and grocery items'
            },
            {
                'slug': 'computers',
                'name': 'Computers & Accessories',
                'description': 'Computers, laptops, and computer accessories'
            },
            {
                'slug': 'phones',
                'name': 'Phones & Tablets',
                'description': 'Smartphones, tablets, and mobile devices'
            },
            {
                'slug': 'jewelry',
                'name': 'Jewelry & Watches',
                'description': 'Jewelry, watches, and accessories'
            },
            {
                'slug': 'baby',
                'name': 'Baby Products',
                'description': 'Baby clothing, toys, and care products'
            },
            {
                'slug': 'pets',
                'name': 'Pet Supplies',
                'description': 'Pet food, toys, and pet care products'
            },
            {
                'slug': 'office',
                'name': 'Office Products',
                'description': 'Office supplies and workspace equipment'
            },
            {
                'slug': 'gaming',
                'name': 'Video Games & Consoles',
                'description': 'Video games, consoles, and gaming accessories'
            },
        ]

        created_count = 0
        existing_count = 0

        for category_data in DEFAULT_CATEGORIES:
            slug = category_data['slug']
            name = category_data['name']
            
            # Try to get existing category by slug or name
            try:
                category = Category.objects.get(slug=slug)
                existing_count += 1
                self.stdout.write(
                    self.style.WARNING(f'✓ Category already exists: {name}')
                )
            except Category.DoesNotExist:
                # Check if category exists by name
                try:
                    category = Category.objects.get(name=name)
                    existing_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'✓ Category already exists: {name}')
                    )
                except Category.DoesNotExist:
                    # Create new category
                    category = Category.objects.create(
                        slug=slug,
                        name=name,
                        description=category_data.get('description', ''),
                        is_active=True
                    )
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Created category: {name}')
                    )

        total = created_count + existing_count
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Done! Created: {created_count}, Already existed: {existing_count}, Total: {total}'
            )
        )
