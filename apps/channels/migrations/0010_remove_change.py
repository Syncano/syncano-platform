from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0009_eventlog_channel'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='change',
            index_together=set(),
        ),
        migrations.RemoveField(
            model_name='change',
            name='channel',
        ),
        migrations.DeleteModel(
            name='Change',
        ),
    ]
