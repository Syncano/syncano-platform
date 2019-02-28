from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0018_admin_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='admin',
            name='is_trusted',
            field=models.BooleanField(default=False, verbose_name='trusted status'),
        ),
    ]
