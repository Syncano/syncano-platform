# coding=UTF8
from django.test import testcases
from rest_framework.exceptions import ValidationError

from apps.response_templates.validators import Jinja2TemplateValidator


class TestJinja2TemplateValidator(testcases.TestCase):

    def setUp(self):
        self.validator = Jinja2TemplateValidator()
        self.good_template = """<div><ul>{% for i in objects %}<li>{{ i }}</li>{% endfor %}</ul></div>"""
        self.bad_template = """<div><ul>{% for i in objects %}<li>{{ i }}</li>{% endfo %}</ul></div>"""

    def test_validator(self):
        self.validator(self.good_template)  # will raise an error if can't build template

        with self.assertRaises(ValidationError):
            self.validator(self.bad_template)
