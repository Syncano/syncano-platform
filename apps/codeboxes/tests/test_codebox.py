# coding=UTF8
import json
import random
from unittest import mock

from django.conf import settings
from django.test import TestCase, tag
from django_dynamic_fixture import G
from requests import Timeout

from apps.codeboxes.tasks import CodeBoxTask
from apps.codeboxes.tests.mixins import CodeBoxCleanupTestMixin
from apps.core.helpers import verify_token
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.sockets.models import Socket

from ..container_manager import ContainerManager
from ..exceptions import CannotCreateContainer
from ..models import CodeBox, CodeBoxTrace
from ..runner import CodeBoxRunner
from ..runtimes import LATEST_NODEJS_LIB_RUNTIME, LATEST_NODEJS_RUNTIME, LATEST_PYTHON_RUNTIME


def create_codebox_spec(instance, codebox, additional_args=None):
    return CodeBoxTask.create_spec(instance, codebox, additional_args, None)


@tag('legacy_codebox')
@mock.patch('apps.codeboxes.runner.ContainerManager', mock.MagicMock())
@mock.patch('apps.codeboxes.runner.CodeBoxRunner.process_result', mock.MagicMock(return_value={}))
class TestCodeBoxRunner(CodeBoxCleanupTestMixin, TestCase):
    def setUp(self):
        self.instance = G(Instance, name='testtest')
        set_current_instance(self.instance)
        source = 'test'
        runtime_name = LATEST_PYTHON_RUNTIME
        self.codebox = CodeBox.objects.create(label='test',
                                              source=source,
                                              runtime_name=runtime_name)
        self.runner = CodeBoxRunner()

    def test_there_is_trace_after_running_codebox(self):
        self.assertEqual(len(CodeBoxTrace.list(codebox=self.codebox)), 0)
        self.runner.run(create_codebox_spec(self.instance, self.codebox))
        set_current_instance(self.instance)
        self.assertEqual(len(CodeBoxTrace.list(codebox=self.codebox)), 1)


@tag('legacy_codebox')
class TestCodeBoxRunnerIntegration(CodeBoxCleanupTestMixin, TestCase):
    def setUp(self):
        self.instance = G(Instance, name='testtest')

        set_current_instance(self.instance)
        source = "print(\'hello\')"
        runtime_name = LATEST_PYTHON_RUNTIME
        self.runner = CodeBoxRunner()
        self.codebox = CodeBox.objects.create(label='test',
                                              source=source, runtime_name=runtime_name)
        self.codebox_spec = create_codebox_spec(self.instance, self.codebox)

    def test_running_codebox(self):
        result = self.runner.run(self.codebox_spec)
        self.assertTrue(result)

    @mock.patch('apps.codeboxes.tasks.SaveTraceTask.run')
    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.process',
                mock.MagicMock(return_value=(CodeBoxTrace.STATUS_CHOICES.SUCCESS, {})))
    def test_codebox_processing_status(self, update_trace_mock):
        runtime = LATEST_PYTHON_RUNTIME
        self.codebox.runtime_name = runtime
        trace = CodeBoxTrace.create(codebox=self.codebox)
        self.assertEqual(trace.status, trace.STATUS_CHOICES.PENDING)
        CodeBoxTask.delay(self.codebox.id, self.instance.id,
                          additional_args={}, trace_pk=trace.pk)
        set_current_instance(self.instance)
        trace = CodeBoxTrace.get(pk=trace.id)
        self.assertEqual(trace.status, trace.STATUS_CHOICES.PROCESSING)

    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.process', return_value=('success', {}))
    def test_custom_socket_config(self, process_mock):
        config_key_name = 'very_specific_and_unique_name'
        config_val = 'test123'
        socket = G(Socket, config={config_key_name: config_val}, status=Socket.STATUSES.OK)
        self.codebox.socket = socket
        self.codebox.save()

        trace = CodeBoxTrace.create(codebox=self.codebox)
        CodeBoxTask.delay(self.codebox.id, self.instance.id,
                          additional_args={}, trace_pk=trace.pk)
        config = json.loads(process_mock.call_args[0][2]['config'])
        self.assertIn(config_key_name, config)
        self.assertEqual(config[config_key_name], config_val)

    def test_all_runtimes(self):
        runtime_to_sources = {
            'ruby': "require 'syncano'\nputs 'ruby'",
            LATEST_PYTHON_RUNTIME: "import syncano\nprint('{}')".format(LATEST_PYTHON_RUNTIME),
            'python3': "import syncano\nprint('python3')",
            LATEST_NODEJS_RUNTIME: "console.log('{}')".format(LATEST_NODEJS_RUNTIME),
            LATEST_NODEJS_LIB_RUNTIME: "var Syncano = require('syncano');"
                                       "console.log('{}')".format(LATEST_NODEJS_LIB_RUNTIME),
            'golang': "import \"fmt\"; func main() {fmt.Println(\"golang\")}",
            'swift': 'print("swift")',  # care here: swift required double-quote string literals;
            'php': 'echo "php";'
        }
        for runtime, source in runtime_to_sources.items():
            self.codebox.runtime_name = runtime
            self.codebox.source = source
            codebox_spec = create_codebox_spec(self.instance, self.codebox)
            _, result = self.runner.run(codebox_spec)
            result_stdout = result['stdout']
            self.assertEquals(result_stdout, runtime)
            self.assertNotIn('response', result)

    def test_nodejs_context_separation(self):
        self.codebox.runtime_name = LATEST_NODEJS_RUNTIME
        self.codebox.source = "console.log(typeof fs === 'undefined');"
        codebox_spec = create_codebox_spec(self.instance, self.codebox)
        _, result = self.runner.run(codebox_spec)
        result_stdout = result['stdout']
        self.assertEquals(result_stdout, 'true')

    def test_host_in_meta(self):
        self.codebox.runtime_name = LATEST_NODEJS_RUNTIME
        self.codebox.source = "console.log(META['api_host'], META['space_host']);"
        codebox_spec = create_codebox_spec(self.instance, self.codebox)
        _, result = self.runner.run(codebox_spec)
        result_stdout = result['stdout']
        self.assertEquals(result_stdout, '{} {}'.format(settings.API_HOST, settings.SPACE_HOST))

    def test_large_payload(self):
        limit = settings.CODEBOX_PAYLOAD_SIZE_LIMIT - 100
        runtime_to_sources = {
            'ruby': "require 'syncano'\nputs ARGS['payload'].length",
            LATEST_PYTHON_RUNTIME: "import syncano\nprint len(ARGS['payload'])",
            'python3': "import syncano\nprint(len(ARGS['payload']))",
            LATEST_NODEJS_LIB_RUNTIME: "var Syncano = require('syncano');\nconsole.log(ARGS['payload'].length)",
            'golang': "import \"fmt\"; func main() {fmt.Println(len(ARGS[\"payload\"].(string)))}",
            'swift': 'print((ARGS["payload"] as! String).characters.count)',
            'php': 'echo strlen($ARGS["payload"]);'
        }
        for runtime, source in runtime_to_sources.items():
            self.codebox.runtime_name = runtime
            self.codebox.source = source
            codebox_spec = create_codebox_spec(self.instance, self.codebox, {'payload': 'a' * limit})
            _, result = self.runner.run(codebox_spec)
            result_stdout = result['stdout']
            self.assertEquals(result_stdout, str(limit))

    def test_httpresponse(self):
        runtime_to_sources = {
            LATEST_PYTHON_RUNTIME: """
print('{}')
set_response(HttpResponse(201, 'content', 'text/plain'))""",
            LATEST_NODEJS_RUNTIME: """
console.log('{}')
setResponse(new HttpResponse(201, 'content', 'text/plain'))""",
            'php': """
print '{}';
set_response(new HttpResponse(201, 'content', 'text/plain'));""",
            'swift': """
print("{}")
setResponse(HttpResponse(statusCode: 201, content: "content", contentType: "text/plain"))""",
            'ruby': """
puts '{}'
set_response(HttpResponse.new(201, 'content', 'text/plain'))""",
        }
        runtime_to_sources['python3'] = runtime_to_sources[LATEST_PYTHON_RUNTIME]
        for runtime, source in runtime_to_sources.items():
            self.codebox.runtime_name = runtime
            self.codebox.source = source.format(runtime)
            codebox_spec = create_codebox_spec(self.instance, self.codebox)
            _, result = self.runner.run(codebox_spec)
            result_stdout = result['stdout']
            self.assertEquals(result_stdout, runtime)
            result_response = result['response']
            self.assertEquals(result_response, {'status': 201, 'content': 'content', 'content_type': 'text/plain'})

    def test_httpresponse_with_headers(self):
        runtime_to_sources = {
            LATEST_PYTHON_RUNTIME: """
print('{}')
set_response(HttpResponse(201, 'content', 'text/plain', {{'x-abc': '123'}}))""",
            LATEST_NODEJS_RUNTIME: """
console.log('{}')
setResponse(new HttpResponse(201, 'content', 'text/plain', {{'x-abc': '123'}}))""",
            'php': """
print '{}';
set_response(new HttpResponse(201, 'content', 'text/plain', ["x-abc" => "123"]));""",
            'swift': """
print("{}")
setResponse(HttpResponse(statusCode: 201, content: "content", contentType: "text/plain", headers: ["x-abc": "123"]))""",
            'ruby': """
puts '{}'
set_response(HttpResponse.new(201, 'content', 'text/plain', {{"x-abc" => "123"}}))""",
        }
        runtime_to_sources['python3'] = runtime_to_sources[LATEST_PYTHON_RUNTIME]
        for runtime, source in runtime_to_sources.items():
            self.codebox.runtime_name = runtime
            self.codebox.source = source.format(runtime)
            codebox_spec = create_codebox_spec(self.instance, self.codebox)
            _, result = self.runner.run(codebox_spec)
            result_stdout = result['stdout']
            self.assertEquals(result_stdout, runtime)
            result_response = result['response']
            self.assertEquals(result_response, {'status': 201, 'content': 'content', 'content_type': 'text/plain',
                                                'headers': {'x-abc': '123'}})

    def test_codebox_supports_utf(self):
        self.codebox.source = "# coding=UTF8\nprint('żółta gęś')"
        self.codebox.save()
        self.codebox_spec = create_codebox_spec(self.instance, self.codebox)
        status, result = self.runner.run(self.codebox_spec)
        expected_result = "żółta gęś"
        self.assertEquals(expected_result, result['stdout'])
        self.assertEquals(status, 'success')

    def run_long_codebox(self, codebox, timeout=30.0):
        source = """
import time
for x in range(3):
    print(x)
    time.sleep(1)
        """
        codebox.source = source
        codebox.config['timeout'] = timeout
        codebox_spec = create_codebox_spec(self.instance, codebox)
        runtime_name = self.codebox_spec['run']['runtime_name']
        return self.runner.process(self.runner.get_container(runtime_name),
                                   runtime_name,
                                   codebox_spec['run'])

    def test_runner_timeouts_too_long_running_containers(self):
        status, res = self.run_long_codebox(self.codebox, timeout=0.01)
        self.assertEquals(status, 'timeout')
        self.assertTrue(res['stderr'])

    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.process',
                mock.MagicMock(return_value=(CodeBoxTrace.STATUS_CHOICES.SUCCESS, {})))
    @mock.patch('apps.codeboxes.runner.CodeBoxRunner.cleanup_container')
    def test_runner_cleans_up_after_container(self, cleanup_mock):
        runner = CodeBoxRunner()
        runner.run(self.codebox_spec)
        self.assertTrue(cleanup_mock.called)

    def test_full_access_token_creation(self):
        self.codebox.source = "print META.get('token')"
        self.codebox.save()
        self.codebox_spec = create_codebox_spec(self.instance, self.codebox)
        _, result = self.runner.run(self.codebox_spec)
        self.assertEqual(result['stdout'], 'None')

        self.codebox.config['allow_full_access'] = True
        self.codebox.save()
        self.codebox_spec = create_codebox_spec(self.instance, self.codebox)
        _, result = self.runner.run(self.codebox_spec)
        token = result['stdout']
        self.assertEqual(verify_token(token), self.instance.pk)


@tag('legacy_codebox')
class TestContainerManager(CodeBoxCleanupTestMixin, TestCase):
    def setUp(self):
        self.container_manager = ContainerManager()

    def test_codebox_runner_creates_docker_container(self):
        runtime_name = LATEST_PYTHON_RUNTIME
        container_data = self.container_manager.get_container(runtime_name)
        self.assertIn('id', container_data)

    @mock.patch('apps.codeboxes.container_manager.logger')
    def test_raises_error_when_cannot_remove_container(self, logger_mock):
        self.container_manager._remove_container({'id': 'nonexisting', 'tmp_dir': '', 'source_dir': ''})
        self.assertTrue(logger_mock.warning.called)

    @mock.patch('apps.codeboxes.container_manager.logger', mock.Mock())
    @mock.patch('apps.codeboxes.container_manager.docker_client.api.create_container',
                mock.MagicMock(side_effect=Timeout()))
    def test_raises_error_when_cannot_prepare_container(self):
        self.assertRaises(CannotCreateContainer, self.container_manager.prepare_container, LATEST_PYTHON_RUNTIME)


@tag('legacy_codebox')
class TestInstanceConfigInCodeBox(CodeBoxCleanupTestMixin, TestCase):
    def setUp(self):
        self.var = str(random.getrandbits(256))
        self.instance = G(Instance, name='testtest', config={"hello": self.var, "hello2": self.var})
        set_current_instance(self.instance)
        self.runner = CodeBoxRunner()

    def test_runtimes(self):
        TESTS = {
            'python_library_v5.0': "print CONFIG['hello'], CONFIG['hello2']",
            'nodejs_library_v1.0': "console.log(CONFIG['hello'], CONFIG['hello2'])",
            'swift': 'print(CONFIG["hello"]!, CONFIG["hello2"]!)',
            'golang': 'import "fmt";func main() {fmt.Println(CONFIG["hello"], CONFIG["hello2"])}',
            'php': "echo $CONFIG['hello'].' '.$CONFIG['hello2'];",
            'ruby': "puts \"#{CONFIG['hello']} #{CONFIG['hello2']}\""
        }
        for runtime, source in TESTS.items():
            codebox = G(CodeBox, config={'hello2': 'yes'}, runtime_name=runtime, source=source)
            spec = create_codebox_spec(self.instance, codebox)
            status, result = self.runner.run(spec)
            self.assertEqual(status, 'success')
            self.assertEqual(result['stdout'], self.var + ' yes')
