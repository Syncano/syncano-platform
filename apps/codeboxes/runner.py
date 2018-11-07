# coding=UTF8
import datetime
import logging
import os
import socket
import time

import rapidjson as json
from django.conf import settings
from django.utils.encoding import force_bytes
from docker.errors import APIError
from docker.utils.socket import frames_iter
from requests.exceptions import ConnectionError, Timeout

from apps.codeboxes.container_manager import ContainerManager
from apps.core.exceptions import SyncanoException
from apps.core.helpers import docker_client, redis
from apps.response_templates.models import ResponseTemplate

from .exceptions import CannotExecContainer, ScriptWrapperError
from .models import Trace
from .runtimes import RUNTIMES

logger = logging.getLogger(__name__)


class CodeBoxRunner:
    """
    Runner for CodeBox docker containers.
    """

    def __init__(self, logger=None):
        if logger is None:
            logger = logging.getLogger(__name__)
        self.logger = logger
        self.container_manager = ContainerManager

    def run(self, codebox_spec):
        """Run codebox_schedule or just plain codebox.

        :param codebox_spec: codebox spec
        :return: result of codebox execution as a string
        """
        executed_at = datetime.datetime.now().strftime(settings.DATETIME_FORMAT)
        start = time.time()
        run_spec = codebox_spec['run']
        runtime_name = run_spec['runtime_name']

        container_data = self.get_container(runtime_name)
        already_cleaned = False

        # Default result info in case something goes wrong
        result_info = {
            'status': Trace.STATUS_CHOICES.FAILURE,
            'executed_at': executed_at,
        }
        try:
            # Update trace status if trace already exists
            if 'trace' in codebox_spec and codebox_spec['trace']['id']:
                from .tasks import UpdateTraceTask
                UpdateTraceTask.delay(codebox_spec['trace'])

            status, result = self.process(container_data, runtime_name, run_spec)
            result_info['result'] = result
            result_info['status'] = status

            end = time.time()
            result_info['duration'] = int((end - start) * 1000)

            if 'trace' in codebox_spec:
                from .tasks import SaveTraceTask

                SaveTraceTask.delay(codebox_spec['trace'], result_info)
                result_info['id'] = codebox_spec['trace']['id']

            if 'template' in codebox_spec:
                self.process_template(instance=codebox_spec['run']['instance'],
                                      template_spec=codebox_spec['template'],
                                      result_info=result_info)

            if 'result_key' in codebox_spec:
                self.publish_result_info(codebox_spec['result_key'], result_info)

            schedule_next_info = codebox_spec.get('schedule_next')
            if schedule_next_info:
                from .tasks import ScheduleNextTask

                ScheduleNextTask.delay(**schedule_next_info)
        except ScriptWrapperError:
            # Handle script wrapper errors separately - always dispose of container
            # as there may be some lingering processes
            self.dispose_container(runtime_name, container_data)
            already_cleaned = True
            raise
        finally:
            if not already_cleaned:
                self.cleanup_container(runtime_name, container_data)
        return status, result

    @staticmethod
    def format_codebox_sourcecode(run_spec, separator):
        runtime_name = run_spec['runtime_name']
        if runtime_name == 'swift':
            for spec_name in ('meta', 'config', 'additional_args'):
                # to avoid error in swift with multiple double quotes
                run_spec[spec_name] = run_spec[spec_name].replace('"', '\\"')
        return RUNTIMES[runtime_name]['source_template'].format(separator=separator, **run_spec)

    @staticmethod
    def publish_result_info(result_key, result_info):
        if 'result' in result_info and 'response' in result_info['result']:
            serialized_result = '!{}'.format(json.dumps(result_info['result']['response']))
        else:
            serialized_result = json.dumps(result_info)
        redis.publish(result_key, serialized_result)

    @staticmethod
    def process_template(instance, template_spec, result_info):
        context = {'response': result_info,
                   'instance': instance,
                   'action': 'script'}
        context.update(template_spec['context'])
        if 'result' not in result_info:
            result_info['result'] = {}

        try:
            response = ResponseTemplate.render_template(content=template_spec['content'],
                                                        data=result_info,
                                                        context=context)
        except SyncanoException as ex:
            result_info['result']['response'] = {'status': ex.status_code,
                                                 'content_type': 'application/json; charset=utf-8',
                                                 'content': ex.detail}
            return

        # Modify response, preserve status code if needed
        status = 200
        if 'response' in result_info['result']:
            status = result_info['result']['response']['status']

        result_info['result']['response'] = {'status': status,
                                             'content_type': template_spec['content_type'],
                                             'content': response}

    def get_container(self, runtime_name):
        return self.container_manager.get_container(runtime_name)

    def cleanup_container(self, runtime_name, container_data):
        try:
            self.container_manager.cleanup_container(container_data, runtime_name)
        except Exception:
            self.logger.warning("Cleanup wasn't fully successful, deleting container and recreating it.", exc_info=1)
            self.dispose_container(runtime_name, container_data)

    def dispose_container(self, runtime_name, container_data):
        self.container_manager.dispose_container(container_data)
        self.container_manager.prepare_container(runtime_name)

    def execute_script(self, container_data, command, timeout):
        """
        Wait for script to stop and get it's results
        """
        try:
            cmd = "sh -c 'timeout -s INT -k {force_timeout} {timeout} " \
                  "{command} " \
                  "> /tmp/stdout 2> /tmp/stderr || echo $?'".format(timeout=timeout,
                                                                    force_timeout=timeout + 3,  # send kill after +3s
                                                                    command=command)

            execute = docker_client.api.exec_create(container_data['id'], cmd)
            exec_socket = docker_client.api.exec_start(execute['Id'], socket=True)
            if hasattr(exec_socket, '_sock'):
                exec_socket = exec_socket._sock
            return self.handle_exec_socket(exec_socket, timeout)
        except (ConnectionError, APIError, socket.timeout, Timeout, ValueError) as e:
            self.logger.warning("Couldn't exec on container, %s.", container_data['id'], exc_info=1)
            raise CannotExecContainer(str(e))

    def execute_wrapper(self, container_data, context, timeout):
        """
        Connect to wrapper through docker exec socket, send context and get it's results
        """
        exec_socket = container_data['wrapper_socket']
        # prepare context - as it already consists of some keys with encoded json,
        # we prepare it manually to avoid double decode/encode
        context = ','.join(['"{key}":{val}'.format(key=key, val=val) for key, val in context.items()])
        context = '{{{data},"_TIMEOUT":{timeout}}}'.format(data=context, timeout=timeout)

        try:
            exec_socket.sendall(force_bytes(context))
            exec_socket.sendall(b'\n')
            return self.handle_exec_socket(exec_socket, timeout)
        except (ConnectionError, APIError, socket.timeout, ValueError, IOError) as e:
            self.logger.warning("Couldn't handle wrapper socket on container, %s.", container_data['id'], exc_info=1)
            raise ScriptWrapperError(str(e))

    def handle_exec_socket(self, exec_socket, timeout):
        try:
            # exec_start does not support timeout normally so we need to process timeout on raw socket.
            # As we are already running timeout script inside container, add some grace period (5s) to socket timeout.
            exec_socket.settimeout(timeout + 5)
            exec_result = b''.join(frames_iter(exec_socket))
            exit_code = int(exec_result) if exec_result else 0

            if exit_code == 0:
                status = Trace.STATUS_CHOICES.SUCCESS
            elif exit_code == 124:
                # timeout command returns with 124 exit code when time out occurs
                status = Trace.STATUS_CHOICES.TIMEOUT
            else:
                status = Trace.STATUS_CHOICES.FAILURE
        except socket.timeout:
            status = Trace.STATUS_CHOICES.TIMEOUT
        finally:
            exec_socket.close()

        return status

    def process(self, container_data, runtime_name, run_spec):
        """
        Prepare source code script, start it and collect results.
        """
        runtime = RUNTIMES[runtime_name]
        run_as_wrapper = runtime.get('wrapper')
        separator = '--{}--'.format(container_data['id'])

        if run_as_wrapper:
            user_source = run_spec['original_source']
        else:
            user_source = self.format_codebox_sourcecode(run_spec, separator)

        source_name = '{name}.{file_ext}'.format(
            name=settings.CODEBOX_MOUNTED_SOURCE_ENTRY_POINT,
            file_ext=runtime['file_ext']
        )
        with open(os.path.join(container_data['source_dir'], source_name), 'w') as f:
            f.write(user_source)

        if run_as_wrapper:
            status = self.execute_wrapper(container_data, context={'ARGS': run_spec['additional_args'],
                                                                   'CONFIG': run_spec['config'],
                                                                   'META': run_spec['meta'],
                                                                   '_OUTPUT_SEPARATOR': '"{}"'.format(separator)},
                                          timeout=run_spec['timeout'])
        else:
            source_on_container = os.path.join(settings.CODEBOX_MOUNTED_SOURCE_DIRECTORY, source_name)
            command = runtime['command'].format(source_file=source_on_container)

            status = self.execute_script(container_data, command, timeout=run_spec['timeout'])
        return status, self.process_result(container_data, separator)

    def process_result(self, container_data, separator):
        max_stream_length = settings.CODEBOX_RESULT_SIZE_LIMIT
        with open(os.path.join(container_data['tmp_dir'], 'stdout')) as f:
            stdout = f.read(max_stream_length)

        max_stream_length -= len(stdout)
        with open(os.path.join(container_data['tmp_dir'], 'stderr')) as f:
            stderr = f.read(max_stream_length).rstrip('\n')

        result = {
            'stderr': stderr
        }

        if separator in stdout:
            stdout, response = stdout.rsplit(separator, 1)
            try:
                status_code, content_type, content, headers = json.loads(response)
            except ValueError:
                result['stderr'] = 'stdout and/or stderr max size exceeded.'
            else:
                try:
                    result['response'] = {'status': int(status_code),
                                          'content_type': str(content_type),
                                          'content': str(content)}
                    if headers:
                        if not isinstance(headers, dict):
                            raise ValueError('Headers are expected to be a dict.')
                        result['response']['headers'] = headers
                except (TypeError, ValueError, UnicodeDecodeError):
                    result = {'stderr': 'Incorrect custom response received.'}

        result['stdout'] = stdout.rstrip('\n')
        return result
