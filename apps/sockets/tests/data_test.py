# coding=UTF8
from io import BytesIO
from zipfile import ZipFile

SOCKET_YML = """
name: custom_socket_example
author:
  name: Info
  email: info@synano.com
keywords:
  - one
  - two
classes:
  default:
    - name: field1
      type: integer
config:
  secret_key:
    value: custom_api_key
  user_key:
    value: user_key
description: Some custom integration
endpoints:
  custom_endpoint:
    file: scripts/custom_script_1.py

  custom_endpoint_1:
    POST:
      file: scripts/custom_script_2.py
    GET:
      file: scripts/custom_script_3.py
"""


CUSTOM_SCRIPT_1 = {
    'source': """
print('GET: custom_endpoint')
""",
    'name': 'custom_script_1.py'
}

CUSTOM_SCRIPT_2 = {
    'source': """
print('GET: custom_endpoint_1')
""",
    'name': 'custom_script_2.py'
}

CUSTOM_SCRIPT_3 = {
    'source': """
print('POST: custom_endpoint_1')
""",
    'name': 'custom_script_3.py'
}

HELPER_SCRIPT_1 = {
    'source': """
helper script content
""",
    'name': 'helper_script_1.py'
}

HELPER_SCRIPT_2 = {
    'source': """
helper script 2 content
""",
    'name': 'helper_script_2.py'
}


def pack_test_data_into_zip_file(yml_definition, scripts):
    content = BytesIO()
    with ZipFile(content, 'w') as myzip:
        myzip.writestr('socket.yml', yml_definition)

        for script in scripts:
            myzip.writestr('scripts/{}'.format(script['name']), script['source'])
        myzip.close()

    content.seek(0)
    return content.read()


def pack_test_data_without_yml(scripts):
    content = BytesIO()
    with ZipFile(content, 'w') as myzip:
        for script in scripts:
            myzip.writestr('scripts/{}'.format(script['name']), script['source'])
        myzip.close()

    content.seek(0)
    return content.read()


def pack_test_data_without_scripts(yml_definition):
    content = BytesIO()
    with ZipFile(content, 'w') as myzip:
        myzip.writestr('socket.yml', yml_definition)

    content.seek(0)
    return content.read()
