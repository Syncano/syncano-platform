# coding=UTF8
from apps.codeboxes.container_manager import ContainerManager
from apps.core.tests.mixins import CleanupTestCaseMixin


class CodeBoxCleanupTestMixin(CleanupTestCaseMixin):
    def tearDown(self):
        super().tearDown()
        ContainerManager.dispose_all_containers()
