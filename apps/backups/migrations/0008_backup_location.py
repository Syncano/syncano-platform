from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backups', '0007_backup_size_to_int64'),
    ]

    operations = [
        migrations.AddField(
            model_name='backup',
            name='location',
            field=models.TextField(db_index=True, default=settings.LOCATION),
        ),
    ]
