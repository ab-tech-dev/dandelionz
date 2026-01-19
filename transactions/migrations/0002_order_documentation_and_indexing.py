# Generated migration for improving Order model documentation and indexing

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0001_initial'),
    ]

    operations = [
        # Add db_index and help_text to order_id
        migrations.AlterField(
            model_name='order',
            name='order_id',
            field=models.UUIDField(db_index=True, editable=False, help_text='Public order reference ID', unique=True),
        ),
        # Add help_text to status
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('PAID', 'Paid'), ('SHIPPED', 'Shipped'), ('DELIVERED', 'Delivered'), ('RETURNED', 'Returned'), ('CANCELED', 'Canceled')], default='PENDING', help_text='Current order fulfillment status', max_length=10),
        ),
    ]
