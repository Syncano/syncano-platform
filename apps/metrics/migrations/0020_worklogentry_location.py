from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0019_codebox_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='worklogentry',
            name='location',
            field=models.TextField(db_index=True, default=settings.LOCATION),
        ),
    ]
