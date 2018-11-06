# coding=UTF8
from apps.codeboxes.permissions import ProtectScriptAccess


class ProtectScriptEndpointAccess(ProtectScriptAccess):
    """
    Disallow editing script endpoints that are not bound to socket.
    """
    allowed_actions = ('retrieve', 'run', 'endpoint_get', 'endpoint_post',
                       'endpoint_patch', 'endpoint_put', 'endpoint_delete')
