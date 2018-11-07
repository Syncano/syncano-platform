# coding=UTF8
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django_dynamic_fixture import G

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.hosting.models import Hosting


@mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.delay', mock.Mock())
class TestHostingBase(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()

        self.hosting = G(Hosting, name='test_name', description='test_description', is_default=True)
        self.create_file_url = reverse('v1.1:hosting-file-list', args=(self.instance.name, self.hosting.id))

    def _post_file(self, file_content, path='index.html'):
        tmp_file = SimpleUploadedFile('index.html', file_content.encode(), content_type='text/html')
        response = self.client.post(
            self.create_file_url,
            data={
                'file': tmp_file,
                'path': path
            },
            format='multipart',
            HTTP_HOST_TYPE='api',
        )
        return response
