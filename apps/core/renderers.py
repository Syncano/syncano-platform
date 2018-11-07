from tempfile import NamedTemporaryFile

import pdfkit
import rapidjson as json
from django.core.exceptions import ImproperlyConfigured
from django.template import engines, loader
from rest_framework.renderers import BaseRenderer
from rest_framework.renderers import JSONRenderer as _JSONRenderer

from apps.core.helpers import evaluate_promises


class JSONRenderer(_JSONRenderer):
    """
    Renderer which serializes to JSON.
    Does *not* apply JSON's character escaping for non-ascii characters.
    """

    ensure_ascii = False
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Render `data` into JSON.
        """
        if data is None:
            return bytes()

        # If 'indent' is provided in the context, then pretty print the result.
        # E.g. If we're being called by the BrowsableAPIRenderer.
        renderer_context = renderer_context or {}
        indent = self.get_indent(accepted_media_type, renderer_context)

        if indent:
            ret = json.dumps(data, indent=indent, ensure_ascii=self.ensure_ascii, number_mode=json.NM_NATIVE)
        else:
            # C json does not handle lazy proxy objects from validation errors
            # so we need to convert them manually here.
            data = evaluate_promises(data)
            ret = json.dumps(data, ensure_ascii=self.ensure_ascii, number_mode=json.NM_NATIVE)

        return ret.encode()


class PDFRenderer(BaseRenderer):
    media_type = 'application/pdf'
    format = 'pdf'
    charset = None
    render_style = 'binary'
    pdf_template_name = None
    pdf_template_context = None
    pdf_filename = 'file.pdf'
    pdf_toc = None
    pdf_cover = None
    pdf_css = None
    pdf_options = options = {
        'margin-top': '0.0in',
        'margin-right': '0.0in',
        'margin-bottom': '0.0in',
        'margin-left': '0.0in',
        'encoding': 'UTF-8',
        'quiet': ''
    }
    pdf_exception_template_names = [
        'pdf_%(status_code)s.html',
        'pdf_exception.html'
    ]

    def render(self, data, media_type=None, renderer_context=None):
        """
        Renders data to PDF, using Django's standard template rendering and pdfkit.
        The pdf template name is determined by (in order of preference):
        1. An explicit .pdf_template_name set on the response.
        2. An explicit .pdf_template_name set on this class.
        3. The return result of calling view.get_pdf_template_name().
        """
        renderer_context = renderer_context or {}
        view = renderer_context['view']
        request = renderer_context['request']
        response = renderer_context['response']

        if response.exception:
            template = self.get_exception_template(response)
        else:
            template_names = self.get_pdf_template_names(response, view)
            template = self.resolve_template(template_names)

        context = self.resolve_context(data, response, view)
        content = template.render(context, request)

        pdf_filename = self.get_pdf_filename(response, view)

        options = {
            'options': self.get_pdf_options(response, view),
            'toc': self.get_pdf_toc(response, view),
            'cover': self.get_pdf_cover(response, view),
            'css': self.get_pdf_css(response, view),
        }

        with NamedTemporaryFile() as f:
            pdfkit.from_string(content, f.name, **options)
            pdf = f.read()

        response['Content-Disposition'] = 'attachment; filename=%s' % pdf_filename

        return pdf

    def resolve_template(self, template_names):
        return loader.select_template(template_names)

    def resolve_context(self, data, response, view):
        context = self.get_pdf_template_context(response, view) or {}
        context['data'] = data

        if response.exception:
            context['status_code'] = response.status_code

        return context

    def _get_attr(self, attr_name, response, view, silent=False):
        if hasattr(response, attr_name):
            return getattr(response, attr_name)
        elif hasattr(view, 'get_%s' % attr_name):
            get_attr = getattr(view, 'get_%s' % attr_name)
            return get_attr()
        elif hasattr(view, attr_name):
            return getattr(view, attr_name)
        elif hasattr(self, attr_name):
            return getattr(self, attr_name)

        if not silent:
            raise ImproperlyConfigured('Attribute `%s` is required on the view or response.' % attr_name)

    def get_pdf_template_names(self, response, view):
        template_names = self._get_attr('pdf_template_name', response, view)
        if not isinstance(template_names, (list, tuple)):
            template_names = [template_names]
        return template_names

    def get_pdf_options(self, response, view):
        return self._get_attr('pdf_options', response, view, silent=True)

    def get_pdf_filename(self, response, view):
        return self._get_attr('pdf_filename', response, view, silent=True)

    def get_pdf_template_context(self, response, view):
        return self._get_attr('pdf_template_context', response, view, silent=True)

    def get_pdf_toc(self, response, view):
        return self._get_attr('pdf_toc', response, view, silent=True)

    def get_pdf_cover(self, response, view):
        return self._get_attr('pdf_cover', response, view, silent=True)

    def get_pdf_css(self, response, view):
        return self._get_attr('pdf_css', response, view, silent=True)

    def get_exception_template(self, response):
        template_names = [name % {'status_code': response.status_code}
                          for name in self.pdf_exception_template_names]

        try:
            # Try to find an appropriate error template
            return self.resolve_template(template_names)
        except Exception:
            # Fall back to using eg '404 Not Found'
            return engines['django'].from_string('%d %s' % (response.status_code,
                                                            response.status_text.title()))
