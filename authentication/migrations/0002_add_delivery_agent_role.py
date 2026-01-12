# Generated migration for adding DELIVERY_AGENT role to CustomUser

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('ADMIN', 'Admin'),
                    ('BUSINESS_ADMIN', 'Business Admin'),
                    ('VENDOR', 'Vendor'),
                    ('CUSTOMER', 'Customer'),
                    ('DELIVERY_AGENT', 'Delivery Agent'),
                ],
                default='CUSTOMER',
                max_length=20
            ),
        ),
    ]
