# coding=UTF8
from apps.response_templates.models import ResponseTemplate


class PredefinedTemplates:

    fields_to_skip = [
        "id",
        "channel",
        "channel_room",
        "group",
        "links",
        "group_permissions",
        "owner_permissions",
        "other_permissions",
        "owner",
        "revision",
        "updated_at",
        "created_at"
    ]

    templates = [
        {
            'name': 'objects_html_table',
            'content': """
{% if action == 'list' %}
    {% set objects = response.objects %}
{% elif action == 'retrieve' %}
    {% set objects = [response] %}
{% else %}
    {% set objects = [] %}
{% endif %}
{% if objects %}
    <table{% if table_classes %} class="{{ table_classes }}"{% endif %}>

    <tr{% if tr_header_classes %} class="{{ tr_header_classes }}"{% endif %}>
        {% for key in objects[0] if key not in fields_to_skip %}
            <th{% if th_header_classes %} class="{{ th_header_classes }}"{% endif %}>{{ key }}</th>
        {% endfor %}
    </tr>
    {% for object in objects %}
        <tr{% if tr_row_classes %} class="{{ tr_row_classes }}"{% endif %}>
        {% for key, value in object.items() if key not in fields_to_skip %}
            <td{% if td_row_classes %} class="{{ td_row_classes }}"{% endif %}>{{ value }}</td>
        {% endfor %}
        </tr>
    {% endfor %}
    </table>
{% endif %}
""",
            'context': {
                "table_classes": "",
                "tr_header_classes": "",
                "th_header_classes": "",
                "tr_row_classes": "",
                "td_row_classes": "",
                "fields_to_skip": fields_to_skip,
            },
            'content_type': 'text/html',
        },
        {
            'name': 'objects_csv',
            'content': """{% if action == 'list' %}
    {% set objects = response.objects %}
{% elif action == 'retrieve' %}
    {% set objects = [response] %}
{% else %}
    {% set objects = [] %}
{% endif %}
{% if objects %}
    {% for key in objects[0] if key not in fields_to_skip %}
        {% if loop.index0 > 0 %}
            {{- delimiter -}}
        {% endif %}
        {{- key -}}
    {% endfor %}
    {{- newline -}}
    {% for object in objects %}
        {% for key, value in object.items() %}
            {% if key not in fields_to_skip %}
                {% if loop.index0 > 0 %}
                    {{- delimiter -}}
                {% endif %}
                {{- '"' }}{{ value }}{{ '"' -}}
            {% endif %}
        {% endfor %}
        {{ newline -}}
    {% endfor %}
{% endif %}
""",
            'context': {
                "newline": "\n",
                "delimiter": ",",
                "fields_to_skip": fields_to_skip,
            },
            'content_type': 'text/csv',
        },
    ]

    @classmethod
    def create_template_responses(cls, check=False, model=None):
        model = model or ResponseTemplate
        templates = []
        for template in cls.templates:
            if check and model.objects.filter(name=template['name']).exists():
                continue
            templates.append(model(**template))

        if templates:
            model.objects.bulk_create(templates)
