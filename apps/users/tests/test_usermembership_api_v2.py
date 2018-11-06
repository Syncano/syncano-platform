from django.urls import reverse

from apps.users.tests import test_usermembership_api as tests_v1


class TestUserGroupList(tests_v1.TestUserGroupList):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:user-group-list', args=(self.instance.name, self.user.id))


class TestUserGroupListKeyAccess(tests_v1.TestUserGroupListKeyAccess):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:user-group-list', args=(self.instance.name, self.user.id))


class TestUserGroupDetail(tests_v1.TestUserGroupDetail):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:user-group-detail', args=(self.instance.name, self.user.id, self.group.id))
