#!/usr/bin/env python
"""
Checks if celery workers are alive to prevent too early container swapping during deploy.

"""
import socket
import xmlrpclib

from docker import Client
from retrying import retry

TIME_BETWEEN_CHECKS = 10000
TIMES_TRYING = 3


def get_new_container_ip_address():
    docker_client = Client(version='auto')
    container_ids = [i['Id'] for i in docker_client.containers()
                     if 'sleep infinity' not in i['Command']]

    if len(container_ids) <= 1:
        return None, True

    containers_info = map(docker_client.inspect_container, container_ids)
    new_container = max(containers_info, key=lambda x: x['State']['StartedAt'])

    return new_container['NetworkSettings']['IPAddress'], False


def retry_if_sock_error(exception):
    return isinstance(exception, socket.error)


@retry(retry_on_exception=retry_if_sock_error,
       stop_max_attempt_number=TIMES_TRYING,
       wait_fixed=TIME_BETWEEN_CHECKS)
def connect_with_supervisor_http(server_ip):
    server = xmlrpclib.Server('http://{}:9001/RPC2'.format(server_ip))
    state = server.supervisor.getState()
    if state['statename'] == 'RUNNING':
        return server


def retry_if_false(result):
    return result is False


@retry(retry_on_result=retry_if_false,
       stop_max_attempt_number=TIMES_TRYING,
       wait_fixed=TIME_BETWEEN_CHECKS)
def check_workers_status(server):
    all_proc_info = server.supervisor.getAllProcessInfo()
    return all(i['statename'] == 'RUNNING' for i in all_proc_info)


def main():
    ip, is_scaling = get_new_container_ip_address()

    if is_scaling:
        return

    server = connect_with_supervisor_http(ip)
    check_workers_status(server)


if __name__ == '__main__':
    main()
