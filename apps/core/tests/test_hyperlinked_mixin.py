from collections import defaultdict
from datetime import datetime
from unittest import mock

from django.http import HttpRequest
from django.test import TestCase
from django.urls import NoReverseMatch
from rest_framework import serializers
from rest_framework.versioning import NamespaceVersioning

from apps.core.mixins.serializers import HyperlinkedMixin


class Comment:
    def __init__(self, email, content, created=None):
        self.pk = 1
        self.email = email
        self.content = content
        self.created = created or datetime.now()


class CommentSerializer(HyperlinkedMixin, serializers.Serializer):
    hyperlinks = (
        ('self', 'apikey-detail', ('content', 'pk', )),
    )

    email = serializers.EmailField()
    content = serializers.CharField(max_length=200)
    created = serializers.DateTimeField()

    def update(self, instance, validated_data):
        instance.email = validated_data.get('email', instance.email)
        instance.content = validated_data.get('content', instance.content)
        instance.created = validated_data.get('created', instance.created)
        instance.save()
        return instance

    def create(self, validated_data):
        return Comment.objects.create(**validated_data)


class HyperlinkedMixinTestCase(TestCase):

    def setUp(self):
        self.comment = Comment(email='leila@example.com', content='foobar')
        self.serializer = CommentSerializer(self.comment)
        request = HttpRequest()
        request.version = 'v1'
        request.META = defaultdict(int)
        request.versioning_scheme = NamespaceVersioning()
        self.serializer._context = {'request': request}
        self.field = self.serializer.fields['links']

    def test_get_attr(self):
        self.field.context['view'] = mock.Mock(kwargs={'test': 1})

        self.assertEqual(
            self.field._get_attr(self.comment, 'email'),
            self.comment.email
        )

        self.assertEqual(self.field._get_attr(self.comment, 'test'), 1)

    def test_get_obj_attr(self):
        self.assertEqual(
            self.field._get_obj_attr(self.comment, 'email'),
            self.comment.email
        )

        self.assertEqual(
            self.field._get_obj_attr(self.comment, 'content'),
            self.comment.content
        )

        self.assertEqual(
            self.field._get_obj_attr(self.comment, 'created'),
            self.comment.created
        )

        self.assertFalse(self.field._get_obj_attr(self.comment, 'dummy'))

    def test_nested_get_attr(self):
        self.field.context['view'] = mock.Mock(kwargs={'test': 1})

        self.assertEqual(
            self.field._get_attr(self.comment, 'created.hour'),
            self.comment.created.hour
        )

        self.assertEqual(
            self.field._get_attr(self.comment, 'created.day'),
            self.comment.created.day
        )

        self.assertRaises(RuntimeError, self.field._get_attr, self.comment, 'dummy.dummy')

    def test_get_view_attr(self):
        self.field.context['view'] = mock.Mock(kwargs={'test': 1})
        self.assertFalse(self.field._get_view_attr('invalid'))
        self.assertEqual(self.field._get_view_attr('test'), 1)

    def test_empty_hyperlinks(self):
        self.field.hyperlinks = ()
        data = self.serializer.data
        self.assertTrue('links' in data)
        self.assertEqual(data['links'], {})

    def test_get_hyperlinks(self):
        data = self.serializer.data
        self.assertTrue('links' in data)
        self.assertTrue('self' in data['links'])

    def test_invalid_hyperlinks(self):
        self.field.hyperlinks = (
            ('self', 'dummy', ('pk',)),
        )

        with self.assertRaises(NoReverseMatch):
            self.serializer.data
