# coding=UTF8
from django.conf import settings
from django.test import TestCase, tag
from django.utils.timezone import now
from django_dynamic_fixture import G

from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.codeboxes.tests.mixins import CodeBoxCleanupTestMixin
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance

from ..models import CodeBox, CodeBoxTrace
from ..tasks import CodeBoxRunTask, CodeBoxTask, SaveTraceTask


class TaskTestBase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.instance = G(Instance, name='testtest')
        set_current_instance(self.instance)


class TestCodeBoxTask(CodeBoxCleanupTestMixin, TaskTestBase):
    def create_codebox(self):
        source = "print(\'hello\')"
        runtime_name = LATEST_PYTHON_RUNTIME
        codebox = CodeBox.objects.create(label='test',
                                         source=source, runtime_name=runtime_name)
        return codebox

    @tag('legacy_codebox')
    def test_running_task(self):
        codebox = self.create_codebox()
        CodeBoxTask.delay(incentive_pk=codebox.id, instance_pk=self.instance.pk)

        set_current_instance(self.instance)
        self.assertEqual(CodeBoxTrace.list(codebox=codebox)[0].result['stdout'], "hello")

    def test_if_task_will_exit_after_empty_spec(self):
        result = CodeBoxRunTask.process_spec(spec_key='nosuchspec')
        self.assertIsNone(result)


class TestTraceSaving(TaskTestBase):
    def test_if_new_trace_is_saved(self):
        codebox = G(CodeBox)
        trace_spec = CodeBoxTask.create_trace_spec(self.instance, codebox)

        result_info = {'executed_at': now().strftime(settings.DATETIME_FORMAT),
                       'result': 'awesome', 'status': 'success', 'duration': 100}
        self.assertEqual(len(CodeBoxTrace.list(codebox=codebox)), 0)
        SaveTraceTask.delay(trace_spec, result_info)
        self.assertEqual(len(CodeBoxTrace.list(codebox=codebox)), 1)

    def test_trace_if_updated_if_its_id_is_passed(self):
        codebox = G(CodeBox)
        trace = CodeBoxTrace.create(codebox=codebox, status="pending")
        trace_spec = CodeBoxTask.create_trace_spec(self.instance, codebox, trace.pk)

        result_info = {'executed_at': now().strftime(settings.DATETIME_FORMAT),
                       'result': 'awesome', 'status': 'success', 'duration': 100}
        self.assertEqual(len(CodeBoxTrace.list(codebox=codebox)), 1)
        self.assertEqual(trace.status, 'pending')
        SaveTraceTask.delay(trace_spec, result_info)
        self.assertEqual(len(CodeBoxTrace.list(codebox=codebox)), 1)
        self.assertEqual(CodeBoxTrace.get(pk=trace.pk).status, 'success')
