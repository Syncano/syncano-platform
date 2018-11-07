# coding=UTF8
import resource
from multiprocessing import Process, Queue, current_process
from queue import Empty

from django.db import models
from jinja2.exceptions import SecurityError
from jsonfield import JSONField

from apps.core.abstract_models import CacheableAbstractModel, DescriptionAbstractModel
from apps.core.fields import StrippedSlugField
from apps.core.helpers import dict_get_any
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS
from apps.response_templates.exceptions import (
    Jinja2TemplateRenderingError,
    TemplateRenderingError,
    TemplateRenderingTimeout,
    UnsafePropertiesOnTemplate
)
from apps.response_templates.jinja2_environments import jinja2_env
from apps.response_templates.utils import get_current_virtual_mememory_size

RESPONSE_TEMPLATE_MAX_LENGTH = 64 * 1024

RESPONSE_TEMPLATE_MEMORY_SOFT_LIMIT = 200 * 1024  # 200MB
RESPONSE_TEMPLATE_MEMORY_HARD_LIMIT = 200 * 1024  # 200MB
RESPONSE_TEMPLATE_CPU_SOFT_TIME_LIMIT = 5  # 2 seconds
RESPONSE_TEMPLATE_CPU_HARD_TIME_LIMIT = 5  # 2 seconds

RESPONSE_TEMPLATE_HEADER_NAMES = ('HTTP_X_TEMPLATE', 'HTTP_X_TEMPLATE_RESPONSE')
RESPONSE_TEMPLATE_GET_ARG_NAMES = ('template', 'template_response')


class ResponseTemplate(DescriptionAbstractModel, CacheableAbstractModel):
    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ},
        'admin': {
            'full': FULL_PERMISSIONS,
            'write': {API_PERMISSIONS.READ},
            'read': {API_PERMISSIONS.READ},
        }
    }

    name = StrippedSlugField(max_length=64, unique=True)
    content_type = models.CharField(max_length=255)
    content = models.TextField(max_length=RESPONSE_TEMPLATE_MAX_LENGTH)
    context = JSONField(default={}, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('id',)
        verbose_name = 'ResponseTemplate'

    def __str__(self):
        return 'ResponseTemplate[id=%s, name=%s, content_type=%s]' % (self.id, self.name, self.content_type)

    @classmethod
    def render_template(cls, content, data=None, context=None):
        """
        Render the jinja2 template;
        :param request: a request object needed for default context;
        :param context: a context passed to the template render method;
        :param data: a response used when some other endpoint is called, passed as a 'response' to the template;
        :return: a rendered content;
        """
        def _render(queue, content, context, current_virtual_memory):
            # limit resources of child process;
            resource.setrlimit(resource.RLIMIT_CPU, (RESPONSE_TEMPLATE_CPU_SOFT_TIME_LIMIT,
                                                     RESPONSE_TEMPLATE_CPU_HARD_TIME_LIMIT))

            # convert to bytes
            soft_memory_limit = (current_virtual_memory + RESPONSE_TEMPLATE_MEMORY_SOFT_LIMIT) * 1024
            hard_memory_limit = (current_virtual_memory + RESPONSE_TEMPLATE_MEMORY_HARD_LIMIT) * 1024
            resource.setrlimit(resource.RLIMIT_AS, (soft_memory_limit, hard_memory_limit))
            try:
                result = {'template': cls.render_raw(content=content, context=context)}
            except Exception as e:
                message = getattr(e, 'message', None) or getattr(e, 'detail', None)
                result = {'error_message': message}
            # put a result to a queue;
            queue.put(result)

        # Workaround for "daemonic processes are not allowed to have children" assertion
        current_process()._config['daemon'] = False

        queue = Queue()
        p = Process(target=_render, args=(queue, content, context, get_current_virtual_mememory_size()))
        p.start()

        try:
            # wait for results from child process;
            render_response = queue.get(timeout=RESPONSE_TEMPLATE_CPU_HARD_TIME_LIMIT)
        except Empty:
            # if timeout occurs - means that render took too much time;
            raise TemplateRenderingTimeout()
        finally:
            # always wait for child processes to terminate;
            p.join(timeout=RESPONSE_TEMPLATE_CPU_HARD_TIME_LIMIT)
            p.terminate()

        if 'error_message' in render_response:
            raise TemplateRenderingError(render_response.get('error_message', None))

        return render_response['template']

    def render(self, request, data=None, context=None):
        """
        Render the jinja2 template;
        :param request: a request object needed for default context;
        :param data: a response used when some other endpoint is called, passed as a 'response' to the template;
        :param context: a context passed to the template render method;
        :return: a rendered content;
        """

        context = context or self.context
        template_context = self._get_default_context(request, data)
        template_context.update(context)  # context is more important;
        return self.render_template(self.content, data, template_context)

    @classmethod
    def get_name_from_request(cls, request):
        return dict_get_any(request.META, *RESPONSE_TEMPLATE_HEADER_NAMES) or \
            dict_get_any(request.GET, *RESPONSE_TEMPLATE_GET_ARG_NAMES)

    @classmethod
    def render_raw(cls, content, context):
        if context.get('action', None) == 'get_api':  # allow to render data endpoints;
            context['action'] = 'list'
        template = jinja2_env.from_string(content)
        try:
            rendered = template.render(context)
        except SecurityError:
            raise UnsafePropertiesOnTemplate()
        except Exception as e:
            raise Jinja2TemplateRenderingError(str(e))
        return rendered

    @classmethod
    def _get_default_context(cls, request, data=None):
        view = request.parser_context['view']
        if not hasattr(view, 'action'):
            raise TemplateRenderingError('This endpoint does not support templates.')
        default_context = {'instance': request.instance.name, 'action': view.action}
        if getattr(request, 'auth_user', None):
            default_context['user'] = request.auth_user.username
        if data:
            default_context['response'] = data
        return default_context
