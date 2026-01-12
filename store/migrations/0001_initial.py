# Generated migration for adding new product fields

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),  # Adjust this based on your users app migrations
    ]

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(blank=True, unique=True)),
                ('description', models.TextField()),
                ('category', models.CharField(choices=[('electronics', 'Electronics'), ('fashion', 'Fashion'), ('home_appliances', 'Home Appliances'), ('beauty', 'Beauty & Personal Care'), ('sports', 'Sports & Outdoors'), ('automotive', 'Automotive'), ('books', 'Books'), ('toys', 'Toys & Games'), ('groceries', 'Groceries'), ('computers', 'Computers & Accessories'), ('phones', 'Phones & Tablets'), ('jewelry', 'Jewelry & Watches'), ('baby', 'Baby Products'), ('pets', 'Pet Supplies'), ('office', 'Office Products'), ('gaming', 'Video Games & Consoles')], max_length=100)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('discounted_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('stock', models.PositiveIntegerField()),
                ('image', models.CharField(blank=True, max_length=255, null=True)),
                ('brand', models.CharField(blank=True, max_length=255, null=True)),
                ('tags', models.TextField(blank=True, help_text='Comma-separated tags or JSON array', null=True)),
                ('variants', models.JSONField(blank=True, help_text='Product variants with color and/or size', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='products', to='users.vendor')),
            ],
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveIntegerField(default=1)),
                ('comment', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='reviews', to='authentication.customuser')),
                ('product', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='reviews', to='store.product')),
            ],
        ),
        migrations.CreateModel(
            name='Favourite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='favourites', to='authentication.customuser')),
                ('product', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='favourited_by', to='store.product')),
            ],
            options={
                'unique_together': {('customer', 'product')},
            },
        ),
        migrations.CreateModel(
            name='CartItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('cart', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='items', to='store.cart')),
                ('product', models.ForeignKey(on_delete=models.deletion.CASCADE, to='store.product')),
            ],
        ),
        migrations.CreateModel(
            name='Cart',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='cart', to='authentication.customuser')),
            ],
        ),
        migrations.AddConstraint(
            model_name='favourite',
            constraint=models.UniqueConstraint(fields=('customer', 'product'), name='unique_customer_product_favourite'),
        ),
    ]
