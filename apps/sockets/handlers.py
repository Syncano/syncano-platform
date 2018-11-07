# coding=UTF8
import logging
import os
from zipfile import ZIP_DEFLATED

import rapidjson as json
import requests
import zipstream
from django.http import StreamingHttpResponse

from apps.async_tasks.handlers import BasicHandler

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

logger = logging.getLogger(__name__)


class SocketZipHandler(BasicHandler):
    def create_zip(self, name, file_list):
        zip = zipstream.ZipFile(mode='w', compression=ZIP_DEFLATED)
        for a_name, url in file_list.items():
            zip.write_iter(a_name, requests.get(url, stream=True).iter_content(chunk_size=16 * 1024))

        response = StreamingHttpResponse(zip, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename={}.zip'.format(name)
        return response

    def get_response(self, request):
        list_file_name = request.environ['LIST_FILE']
        file_name = request.environ['FILE_NAME']

        try:
            with open(list_file_name) as list_file:
                return self.create_zip(file_name, json.load(list_file))
        finally:
            os.unlink(list_file_name)
