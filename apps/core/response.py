# coding=UTF8
from django.http import HttpResponse


class JSONResponse(HttpResponse):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('content_type', 'application/json')
        super().__init__(*args, **kwargs)
