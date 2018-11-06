# coding=UTF8
import urllib.parse

import rapidjson as json


def get_distinct_id(request_data):
    for k, v in request_data.items():
        if 'mixpanel' not in k:
            continue

        try:
            unquoted = urllib.parse.unquote(v)
            return json.loads(unquoted).get('distinct_id')
        except ValueError:
            return None
