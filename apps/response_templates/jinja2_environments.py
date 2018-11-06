# coding=UTF8
import lazy_object_proxy
import rapidjson as json
from jinja2.sandbox import SandboxedEnvironment


def jinja_finalizer(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


jinja2_env = lazy_object_proxy.Proxy(lambda: SandboxedEnvironment(trim_blocks=True,
                                                                  lstrip_blocks=True,
                                                                  finalize=jinja_finalizer))
