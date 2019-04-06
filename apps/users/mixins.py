# coding=UTF8
from apps.data.mixins import ObjectSchemaProcessViewMixin
from apps.data.models import DataObject, Klass


class UserProfileViewMixin(ObjectSchemaProcessViewMixin):
    model = DataObject

    def initialize_request(self, request, *args, **kwargs):
        request = super().initialize_request(request, *args, **kwargs)
        if request.instance:
            self.klass = Klass.get_user_profile()
        return request
