# Generated migration for adding uuid to Product and cart constraints

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        # Add UUID field to Product
        migrations.AddField(
            model_name='product',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        # Change Cart relationship to OneToOne
        migrations.AlterField(
            model_name='cart',
            name='customer',
            field=models.OneToOneField(help_text='Each customer has one active cart', on_delete=django.db.models.deletion.CASCADE, related_name='cart', to=settings.AUTH_USER_MODEL),
        ),
        # Add unique constraint to Cart
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(fields=['customer'], name='one_cart_per_customer'),
        ),
        # Add unique constraint to CartItem
        migrations.AlterUniqueTogether(
            name='cartitem',
            unique_together={('cart', 'product')},
        ),
    ]
