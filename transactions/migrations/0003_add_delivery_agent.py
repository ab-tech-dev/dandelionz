# Generated migration for adding delivery_agent to Order model

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),  # Ensure users app is initialized
        ('authentication', '0002_add_delivery_agent_role'),  # Depend on role addition
        ('transactions', '0002_product_variants_and_more'),  # Depend on previous migration
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='delivery_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_orders', to='users.deliveryagent'),
        ),
        migrations.AddField(
            model_name='order',
            name='assigned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
