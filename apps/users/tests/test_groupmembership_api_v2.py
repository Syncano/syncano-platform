from django.urls import reverse

from apps.users.tests import test_groupmembership_api as tests_v1


class TestGroupUserList(tests_v1.TestGroupUserList):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:group-user-list', args=(self.instance.name, self.group.id))


class TestGroupUserDetail(tests_v1.TestGroupUserDetail):
    def setUp(self):
        super().setUp()
        self.url = reverse('v2:group-user-detail', args=(self.instance.name, self.group.id, self.user.id))
