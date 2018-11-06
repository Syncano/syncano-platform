from django.db import models

from apps.core.helpers import MetaEnum


class AggregateAbstractModel(models.Model):
    class SOURCES(MetaEnum):
        API_CALL = 'api', 'api call'
        CODEBOX_TIME = 'cbx', 'script execution time'

    timestamp = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=3, choices=SOURCES.as_choices())
    admin = models.ForeignKey('admins.Admin', on_delete=models.CASCADE)
    instance_id = models.IntegerField(null=True)
    instance_name = models.CharField(max_length=64, null=True)
    value = models.IntegerField()

    class Meta:
        abstract = True
        ordering = ('id',)

    def __str__(self):
        return '%s[id=%s, timestamp=%s, admin_id=%s, value=%s]' % (
            self.__class__.__name__,
            self.pk,
            self.timestamp,
            self.admin_id,
            self.value
        )
