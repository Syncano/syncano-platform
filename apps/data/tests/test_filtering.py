# coding=UTF8
import json
from datetime import datetime, timedelta

from django.contrib.gis.geos import Point
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.filters.lookups import LOOKUP_PREFIX
from apps.instances.helpers import set_current_instance
from apps.users.models import User

from ..models import DataObject, Klass


class TestAbstractFilterAPI(SyncanoAPITestBase):
    field_types = ('string', 'integer', 'float', 'boolean', 'datetime', 'reference')

    # values calculate for value 5 in setUp
    middle_values = {'string': 'testf',
                     'integer': 5,
                     'float': 15.5,
                     'boolean': False,
                     'datetime': '2000-01-06T00:00:00.000000Z',
                     'reference': 5}
    # objects to create + 1 empty one
    objects_number = 10

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        schema = []
        for field_type in self.field_types:
            field_def = {'name': field_type,
                         'type': field_type,
                         'filter_index': True}
            if field_type == 'reference':
                field_def['target'] = 'self'

            schema.append(field_def)

        self.klass = G(Klass, schema=schema,
                       name='test',
                       description='test')

        django_schema = self.klass.convert_schema_to_django_schema()
        DataObject._meta.get_field('_data').reload_schema(django_schema)

        # Add an empty one as well to test _exists
        self.object_data_list = [
            {'string': None, 'integer': None, 'float': None, 'boolean': None, 'datetime': None, 'reference': None}
        ]
        self.object_data_list += [{'string': 'test%s' % chr(ord('a') + i),
                                   'integer': i,
                                   'float': i * 3.1,
                                   'boolean': i % 2,
                                   'datetime': '%s.000000Z' % (datetime(2000, 1, 1) + timedelta(days=i)).isoformat(),
                                   'reference': i + 1}
                                  for i in range(self.objects_number)]

        for object_data in self.object_data_list:
            data = DataObject(_klass=self.klass, **object_data)
            data.save()
            object_data['_data'] = data

        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def assert_lookup(self, field_type, middle_value):
        query = {field_type: {'%s%s' % (LOOKUP_PREFIX, self.lookup,): middle_value}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        expected_data = []
        expected_ids = []
        for object_data in self.object_data_list:
            if self.cmp(object_data[field_type], middle_value):
                expected_data.append(object_data)
                expected_ids.append(object_data['_data'].id)

        # To make sure we have a valid test case
        self.assertNotEqual(len(response.data['objects']), 0)

        result_ids = [data['id'] for data in response.data['objects']]
        self.assertEqual(result_ids, expected_ids)


def create_filter_test_class(_lookup, _cmp, field_types=None, value=None, value_dict=None, class_name=None):
    class TestFilterAPI(TestAbstractFilterAPI):
        lookup = _lookup
        cmp = _cmp

    field_types = field_types or TestFilterAPI.field_types

    for i, field_type in enumerate(field_types):
        def create_func(field_type, test_value):
            def test_func(self):
                self.assert_lookup(field_type, test_value)

            return test_func

        test_value = value
        if value_dict is None:
            if value is None:
                test_value = TestFilterAPI.middle_values[field_type]
        else:
            test_value = value_dict[field_type]

        setattr(TestFilterAPI, 'test_%s' % field_type, create_func(field_type, test_value))

    class_name = class_name or 'Test%sLookup' % _lookup.capitalize()
    return type(class_name, (TestFilterAPI,), {})


TestGtLookup = create_filter_test_class('gt', lambda self, x, y: x is not None and x > y)
TestGteLookup = create_filter_test_class('gte', lambda self, x, y: x is not None and x >= y)
TestLtLookup = create_filter_test_class('lt', lambda self, x, y: x is not None and x < y,
                                        field_types=('string', 'integer', 'float', 'datetime'))
TestLteLookup = create_filter_test_class('lte', lambda self, x, y: x is not None and x <= y,
                                         field_types=('string', 'integer', 'float', 'datetime'))
TestEqLookup = create_filter_test_class('eq', lambda self, x, y: x == y)
TestNeqLookup = create_filter_test_class('neq', lambda self, x, y: x != y)
TestExistsLookup = create_filter_test_class('exists', lambda self, x, y: x is not None, value=True)
TestNotExistsLookup = create_filter_test_class('exists', lambda self, x, y: x is None, value=False,
                                               class_name='TestNotExistsLookup')

value_dict = {'string': ['testb', 'testf'], 'integer': [3, 5], 'float': [6.2, 15.5],
              'datetime': ['2000-01-03T00:00:00.000000Z', '2000-01-06T00:00:00.000000Z'],
              'boolean': [True], 'reference': [2, 6]}
TestInLookup = create_filter_test_class('in', lambda self, x, y: x in y, value_dict=value_dict)
TestNotInLookup = create_filter_test_class('nin', lambda self, x, y: x not in y, value_dict=value_dict,
                                           class_name='TestNotInLookup')

TestIEqualLookup = create_filter_test_class('ieq',
                                            lambda self, x, y: x.lower() == y.lower() if x is not None else False,
                                            field_types=('string',), value_dict={'string': 'testc'},
                                            class_name='TestIEqualLookup')
TestStartswithLookup = create_filter_test_class('startswith',
                                                lambda self, x, y: x.startswith(y) if x is not None else False,
                                                field_types=('string',), value_dict={'string': 'test'})
TestContainsLookup = create_filter_test_class('contains',
                                              lambda self, x, y: y in x if x is not None else False,
                                              field_types=('string',), value_dict={'string': 'est'})
TestEndswithLookup = create_filter_test_class('endswith',
                                              lambda self, x, y: x.endswith(y) if x is not None else False,
                                              field_types=('string',), value_dict={'string': 'estd'})
TestIStartswithLookup = create_filter_test_class('istartswith',
                                                 lambda self, x, y: x.lower().startswith(y.lower())
                                                 if x is not None else False,
                                                 field_types=('string',), value_dict={'string': 'TEST'},
                                                 class_name='TestIStartswithLookup')
TestIContainsLookup = create_filter_test_class('icontains',
                                               lambda self, x, y: y.lower() in x.lower()
                                               if x is not None else False,
                                               field_types=('string',), value_dict={'string': 'EST'},
                                               class_name='TestIContainsLookup')
TestIEndswithLookup = create_filter_test_class('iendswith',
                                               lambda self, x, y: x.lower().endswith(y.lower())
                                               if x is not None else False,
                                               field_types=('string',), value_dict={'string': 'ESTC'},
                                               class_name='TestIEndswithLookup')


class FilteringTestBase(SyncanoAPITestBase):
    def assert_query_lookup(self, query, expected_count=None, expected_status=status.HTTP_200_OK, order_by=None):
        params = {'query': json.dumps(query)}
        if order_by is not None:
            params['order_by'] = order_by

        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, expected_status)
        if expected_count is not None:
            self.assertEqual(len(response.data['objects']), expected_count)
        return response


class TestReferenceFiltering(FilteringTestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.authors = G(Klass, schema=[{'name': 'name', 'type': 'string', 'filter_index': True}],
                         name='authors')
        self.pages = G(Klass, schema=[{'name': 'count', 'type': 'integer', 'filter_index': True}],
                       name='pages')
        self.books = G(Klass, schema=[{'name': 'name', 'type': 'string'},
                                      {'name': 'author', 'type': 'reference', 'target': 'authors',
                                       'filter_index': True},
                                      {'name': 'page', 'type': 'reference', 'target': 'pages', 'filter_index': True}],
                       name='books')

        # Let's prepare the data set
        books = {'Prus': (('Lalka', 628), ('Faraon', 763), ('Katarynka', 36)),
                 'Sienkiewicz': (('Ogniem i Mieczem', 758), ('Krzyzacy', 794)),
                 'Szymborska': (('Blysk rewolweru', 144), ('Poczta literacka', 236))}
        for author, book_list in books.items():
            DataObject.load_klass(self.authors)
            do_author = DataObject.objects.create(_klass=self.authors, name=author)

            for name, count in book_list:
                DataObject.load_klass(self.pages)
                do_pages = DataObject.objects.create(_klass=self.pages, count=count)
                DataObject.load_klass(self.books)
                DataObject.objects.create(_klass=self.books, name=name, author=do_author.id,
                                          page=do_pages.id)

        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.books.name))

    def test_simple_filtering_by_join(self):
        self.assert_query_lookup({'author': {'_is': {'name': {'_eq': 'Prus'}}}}, 3)
        self.assert_query_lookup({'author': {'_is': {'name': {'_eq': 'Sienkiewicz'}}}}, 2)
        self.assert_query_lookup({'page': {'_is': {'count': {'_gt': 780}}}}, 1)
        self.assert_query_lookup({'author': {'_is': {'name': {'_startswith': 'S'}}}}, 4)
        self.assert_query_lookup({'author': {'_is': {'name': {'_icontains': 'S'}}}}, 7)
        self.assert_query_lookup({'page': {'_is': {'count': {'_gt': 1000}}}}, 0)
        self.assert_query_lookup({'page': {'_is': {'count': {'_in': []}}}}, 0)

    def test_complex_filtering_by_join(self):
        response = self.assert_query_lookup({'author': {'_is': {'name': {'_startswith': 'S'}}},
                                             'page': {'_is': {'count': {'_gt': 200, '_lt': 280}}}}, 1)
        self.assertEqual(response.data['objects'][0]['name'], 'Poczta literacka')

        response = self.assert_query_lookup({'author': {'_is': {'name': {'_iendswith': 'S'}}},
                                             'page': {'_is': {'count': {'_gt': 700, '_lt': 800}}}}, 1)
        self.assertEqual(response.data['objects'][0]['name'], 'Faraon')


class TestArrayFiltering(FilteringTestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'Arr', 'type': 'array', 'filter_index': True}],
                       name='klas')
        DataObject.load_klass(self.klass)
        for arr_data in (['abc', 1, 'bca', '2', '1'],
                         [1, 2, 3],
                         ['1', '2', '3']):
            DataObject.objects.create(_klass=self.klass, Arr=arr_data)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_filtering_validation(self):
        for invalid_query in ({'_eq': ['10']},
                              {'_gt': 10},
                              {'_exists': True},
                              {'_contains': 1}):
            self.assert_query_lookup({'Arr': invalid_query}, expected_status=status.HTTP_400_BAD_REQUEST)

    def test_contains_filtering(self):
        self.assert_query_lookup({'Arr': {'_contains': [1]}}, 2)
        self.assert_query_lookup({'Arr': {'_contains': ['3']}}, 1)
        self.assert_query_lookup({'Arr': {'_contains': ['a']}}, 0)
        self.assert_query_lookup({'Arr': {'_contains': ['1', '2', '3']}}, 1)


class TestLikeFiltering(FilteringTestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'str', 'type': 'string', 'filter_index': True}],
                       name='klas')
        DataObject.load_klass(self.klass)
        for str_data in ('abc', 'ABC', 'Star', 'Superhit', 'AStra', 'data%_a', 'data%%_a'):
            DataObject.objects.create(_klass=self.klass, str=str_data)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_like_filtering(self):
        self.assert_query_lookup({'str': {'_like': 'Star'}}, 1)
        self.assert_query_lookup({'str': {'_like': 'S%'}}, 2)
        self.assert_query_lookup({'str': {'_like': '%S%'}}, 3)
        self.assert_query_lookup({'str': {'_like': 'ab%'}}, 1)
        self.assert_query_lookup({'str': {'_like': 'ab_'}}, 1)
        self.assert_query_lookup({'str': {'_like': 'data\\%\\_a'}}, 1)

    def test_ilike_filtering(self):
        self.assert_query_lookup({'str': {'_ilike': 'Star'}}, 1)
        self.assert_query_lookup({'str': {'_ilike': 'S%'}}, 2)
        self.assert_query_lookup({'str': {'_ilike': '%S%'}}, 3)
        self.assert_query_lookup({'str': {'_ilike': 'AB%'}}, 2)
        self.assert_query_lookup({'str': {'_ilike': 'ab_'}}, 2)


class TestGeoFiltering(FilteringTestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'name', 'type': 'string'},
                                      {'name': 'geo', 'type': 'geopoint', 'filter_index': True}],
                       name='klas')
        DataObject.load_klass(self.klass)
        for name, geo_data in (('Warsaw', Point(21.0122, 52.2297)),
                               ('Krakow', Point(19.9450, 50.0647)),  # 252km distance
                               ('Lodz', Point(19.4560, 51.7592)),  # 119km
                               ('Otwock', Point(21.2616, 52.1053)),  # 21km
                               ('empty', None)):
            DataObject.objects.create(_klass=self.klass, name=name, geo=geo_data)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def assert_distance_lookup(self, point, expected_cities, distance_in_kilometers=None, distance_in_miles=None,
                               order_by=None):
        near_dict = point.copy()
        if distance_in_kilometers is not None:
            near_dict['distance_in_kilometers'] = distance_in_kilometers
        elif distance_in_miles is not None:
            near_dict['distance_in_miles'] = distance_in_miles

        response = self.assert_query_lookup({'geo': {'_near': near_dict}}, len(expected_cities), order_by=order_by)
        objects = response.data['objects']
        self.assertEqual([o['name'] for o in objects], expected_cities)

    def test_point_interpretation(self):
        response = self.client.get(self.url)
        obj = response.data['objects'][0]
        self.assertEqual(obj['geo']['latitude'], 52.2297)
        self.assertEqual(obj['geo']['longitude'], 21.0122)

    def test_filtering_validation(self):
        for invalid_query in ({'_eq': ['10']},
                              {'_gt': 10},
                              {'_near': {'distance_in_kilometers': 1}},
                              {'_near': {'longitude': 179, 'latitude': 90}},
                              {'_near': {'longitude': 180, 'latitude': 89}},
                              {'_near': {'longitude': 179, 'latitude': 89, 'distance_in_kilometers': 40075.1}},
                              {'_near': {'longitude': 179, 'latitude': 89, 'distance_in_kilometers': -1}},
                              {'_near': {'longitude': 179, 'latitude': 89, 'distance_in_miles': 24901.1}},
                              {'_near': {'longitude': 179, 'latitude': 89, 'distance_in_miles': -1}},
                              {'_contains': 1}):
            self.assert_query_lookup({'geo': invalid_query}, expected_status=status.HTTP_400_BAD_REQUEST)

    def test_exists_filtering(self):
        self.assert_query_lookup({'geo': {'_exists': False}}, 1)
        self.assert_query_lookup({'geo': {'_exists': True}}, 4)

    def test_near_filtering(self):
        point = {'longitude': 21.0122, 'latitude': 52.2297}  # Warsaw
        self.assert_distance_lookup(point, ['Warsaw'], distance_in_kilometers=0)
        self.assert_distance_lookup(point, ['Warsaw', 'Otwock'], distance_in_kilometers=100)
        self.assert_distance_lookup(point, ['Warsaw', 'Otwock'], distance_in_miles=30)
        self.assert_distance_lookup(point, ['Warsaw', 'Lodz', 'Otwock'], distance_in_kilometers=120)
        self.assert_distance_lookup(point, ['Warsaw', 'Lodz', 'Otwock'])  # default is 100 miles
        self.assert_distance_lookup(point, ['Warsaw', 'Krakow', 'Lodz', 'Otwock'], distance_in_miles=1000)


class TestRelationFiltering(FilteringTestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.publications = G(Klass, schema=[{'name': 'title', 'type': 'string', 'filter_index': True}],
                              name='publications')
        self.articles = G(Klass, schema=[{'name': 'headline', 'type': 'string', 'filter_index': True},
                                         {'name': 'publications', 'type': 'relation', 'filter_index': True,
                                          'target': 'publications'}],
                          name='articles')

        # Let's prepare the data set
        DataObject.load_klass(self.publications)
        titles = ('The Python Journal', 'Science News', 'Science Weekly')
        self.publication_ids = [DataObject.objects.create(_klass=self.publications, title=title).id for title in titles]

        DataObject.load_klass(self.articles)
        articles = (('Django lets you build Web apps easily', [self.publication_ids[0]]),
                    ('NASA uses Python', self.publication_ids))
        for headline, rel in articles:
            DataObject.objects.create(_klass=self.articles, headline=headline, publications=rel)

        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.articles.name))

    def test_contains_filtering(self):
        self.assert_query_lookup({'publications': {'_contains': [self.publication_ids[0]]}}, 2)
        self.assert_query_lookup({'publications': {'_contains': self.publication_ids}}, 1)
        self.assert_query_lookup({'publications': {'_contains': [123]}}, 0)
        self.assert_query_lookup({'publications': {'_contains': [self.publication_ids[0], 123]}}, 0)
        self.assert_query_lookup({'publications': {'_contains': ['abc']}},
                                 expected_status=status.HTTP_400_BAD_REQUEST)

    def test_filtering_by_join(self):
        self.assert_query_lookup({'publications': {'_is': {'title': {'_startswith': 'Science'}}}}, 1)
        self.assert_query_lookup({'publications': {'_is': {'title': {'_icontains': 'python'}}}}, 2)
        self.assert_query_lookup({'publications': {'_is': {'title': {'_icontains': 'python'}}},
                                  'headline': {'_icontains': 'django'}}, 1)


class TestReferenceUserFiltering(FilteringTestBase):
    disable_user_profile = False

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)

        user_profile = Klass.get_user_profile()
        user_profile.schema = [{'name': 'name', 'type': 'string', 'filter_index': True}]
        user_profile.save()

        self.posts = G(Klass, schema=[{'name': 'name', 'type': 'string'},
                                      {'name': 'user', 'type': 'reference', 'target': 'user',
                                       'filter_index': True}],
                       name='posts')

        # Let's prepare the data set
        # Add one DO first so we shift the IDs of users and DOs
        G(DataObject, _klass=self.posts)

        user_data = (('user1', 'Donald Trump'), ('user2', 'Hillary Clinton'), ('user3', 'Ronald McDonald'),)
        self.users = [User.objects.create(username=user_d[0], password='pass', profile_data={'name': user_d[1]})
                      for user_d in user_data]

        posts = (('post1', self.users[0]), ('post2', self.users[1]), ('post3', self.users[2]),
                 ('post4', self.users[1]), ('post5', self.users[1]), ('post6', self.users[2]))
        DataObject.load_klass(self.posts)
        self.posts_list = [DataObject.objects.create(_klass=self.posts, name=post_d[0], user=post_d[1].id)
                           for post_d in posts]
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.posts.name))

    def test_simple_user_filtering_cases(self):
        response = self.assert_query_lookup({'user': {'_is': {'name': {'_startswith': 'Donald'}}}}, 1)
        self.assertEqual(response.data['objects'][0]['name'], 'post1')

        self.assert_query_lookup({'user': {'_is': {'id': {'_eq': 3}}}}, 2)
        self.assert_query_lookup({'user': {'_is': {'username': {'_eq': 'user2'}}}}, 3)
        self.assert_query_lookup({'user': {'_is': {'name': {'_endswith': 'Donald'}}}}, 2)


class TestUniqueFiltering(FilteringTestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.klass = G(Klass, schema=[{'name': 'name', 'type': 'string', 'filter_index': True, 'unique': True}],
                       name='klas')

        # Let's prepare the data set
        self.klass.refresh_from_db()
        DataObject.load_klass(self.klass)
        for name in ('Warsaw', 'Krakow'):
            DataObject.objects.create(_klass=self.klass, name=name)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_simplefiltering_cases(self):
        self.assert_query_lookup({'name': {'_eq': 'Warsaw'}}, 1)
        self.assert_query_lookup({'name': {'_eq': 'Krakow'}}, 1)
