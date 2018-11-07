from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0023_instance_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='location',
            field=models.TextField(db_index=True, default=settings.LOCATION),
        ),
    ]
