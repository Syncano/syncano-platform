# coding=UTF8
from jinja2.exceptions import TemplateSyntaxError
from rest_framework import serializers

from apps.response_templates.jinja2_environments import jinja2_env


class Jinja2TemplateValidator:

    def __call__(self, value):
        try:
            jinja2_env.from_string(value)
        except TemplateSyntaxError as e:
            raise serializers.ValidationError(e.message)
