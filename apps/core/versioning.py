# coding=UTF8
from rest_framework.versioning import NamespaceVersioning as _NamespaceVersioning


class NamespaceVersioning(_NamespaceVersioning):
    def reverse(self, viewname, args=None, kwargs=None, request=None, format=None, **extra):
        if request.version is not None:
            viewname = self.get_versioned_viewname(viewname, request)
        # We do not want absolute uris so just pass None for request
        return super(_NamespaceVersioning, self).reverse(
            viewname, args, kwargs, None, format, **extra
        )
