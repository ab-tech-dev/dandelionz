from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE users_paymentpin ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT TRUE;",
            reverse_sql="ALTER TABLE users_paymentpin DROP COLUMN IF EXISTS is_default;",
        ),
    ]
