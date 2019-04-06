# coding=UTF8
from apps.data.mixins import ObjectSchemaProcessViewMixin
from apps.data.models import DataObject, Klass


class UserProfileViewMixin(ObjectSchemaProcessViewMixin):
    model = DataObject

    def initial(self, request, *args, **kwargs):
        initial = super().initial(request, *args, **kwargs)
        self.klass = Klass.get_user_profile()
        DataObject.load_klass(self.klass)
        return initial
