#!/usr/bin/env python
import json
import logging
import os
import socket
import subprocess
import sys
import time
from logging import Handler

import requests
from docker import Client, errors
from retrying import RetryError, retry

DOCKER_ERRORS = (errors.DockerException, errors.APIError,
                 requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout)

SLACK_URL = {
    'devel': 'https://hooks.slack.com/services/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',
    'master': 'https://hooks.slack.com/services/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'
}
BRANCH = os.environ.get('SYNCANO_ENV', 'devel')

LOGGING_URL = SLACK_URL[BRANCH]
SLACK_USERNAME = 'docker-watchdog'
SANDBOX_DOCKER_IMAGE = 'quay.io/syncano/script-docker-image:{}'.format(BRANCH)

TIME_BETWEEN_FAILING_CHECKS_MS = 60000
TIME_BETWEEN_CHECKS = 15
TIMES_TRYING = 3

TEST_RUN_TIMEOUT = 10
TEST_DOCKER_IMAGE = 'busybox:latest'

MINIMAL_CHECK_UPTIME = 60 * 6


class SlackLogHandler(Handler):

    def __init__(self, logging_url, slack_username):
        Handler.__init__(self)
        self.logging_url = logging_url
        self.slack_username = slack_username

    def emit(self, record):
        payload = {
            'text': self.formatter.format(record),
            'username': self.slack_username,
        }
        requests.post(self.logging_url, data=json.dumps(payload))


def get_logger():
    log_fmt = '{hostname}: %(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_fmt = log_fmt.format(hostname=socket.gethostname())

    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(log_fmt)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    identifier_command = "/opt/aws/bin/ec2-metadata -i | /bin/awk '{print $2}' | tr -d '\n'"
    slack_log_fmt = '*{hostname}* ({instance_id}): %(name)s - %(message)s'
    slack_log_fmt = slack_log_fmt.format(hostname=socket.gethostname(),
                                         instance_id=subprocess.check_output(identifier_command, shell=True))
    slack_handler = SlackLogHandler(logging_url=LOGGING_URL, slack_username=SLACK_USERNAME)
    slack_formatter = logging.Formatter(slack_log_fmt)
    slack_handler.setFormatter(slack_formatter)
    slack_handler.setLevel(logging.WARNING)

    logger = logging.getLogger('docker-watchdog')
    logger.setLevel(logging.INFO)

    logger.addHandler(console_handler)
    logger.addHandler(slack_handler)
    return logger


LOGGER = get_logger()


@retry(retry_on_result=lambda res: res is False,
       retry_on_exception=lambda exc: isinstance(exc, DOCKER_ERRORS),
       stop_max_attempt_number=TIMES_TRYING,
       wait_fixed=TIME_BETWEEN_FAILING_CHECKS_MS)
def run_docker_check(check):
    return check()


def docker_check():
    try:
        subprocess.check_output(['pidof', 'docker'])
    except subprocess.CalledProcessError:
        LOGGER.error('Docker daemon is down.')
        return False
    LOGGER.info('Docker daemon is up.')
    return True


def container_state_check():

    if BRANCH != 'devel':
        return True

    docker_client = Client(version='auto')
    present_image_ids = {i['Id'] for i in docker_client.images()}
    container_image_ids = {c['ImageID'] for c in docker_client.containers()}
    is_ok = not(container_image_ids - present_image_ids)
    if not is_ok:
        LOGGER.error('Containers without images.')
    else:
        LOGGER.info('Containers are healthy.')

    return is_ok


def run_test_container_check():
    docker_client = Client(version='auto')

    filtered_images = [i for i in docker_client.images()
                       if TEST_DOCKER_IMAGE in i['RepoTags']]

    if not filtered_images:
        LOGGER.error('Testing image not present. Pulling.')
        docker_client.pull(TEST_DOCKER_IMAGE)

    container_info = docker_client.create_container(
        image=TEST_DOCKER_IMAGE,
        command='echo "hello"'
    )
    container_id = container_info['Id']
    docker_client.start(container_id)
    return_code = docker_client.wait(container_id, timeout=TEST_RUN_TIMEOUT)
    docker_client.remove_container(container_id)
    is_ok = return_code == 0

    if not is_ok:
        LOGGER.error('Cannot run container.')
    else:
        LOGGER.info('Running test container succeeded.')
    return is_ok


def is_something_wrong(check):
    try:
        result = run_docker_check(check)
    except DOCKER_ERRORS + (RetryError,):
        return True
    else:
        if not result:
            return True
    return False


def shutdown():
    LOGGER.warning('Shutting down.')
    time.sleep(TIME_BETWEEN_CHECKS)
    subprocess.check_output(['shutdown', '-h', 'now'])
    sys.exit(1)


if __name__ == '__main__':

    LOGGER.info('Watchdog started.')

    while True:
        time.sleep(TIME_BETWEEN_CHECKS)

        if any(map(is_something_wrong, [docker_check, container_state_check, run_test_container_check])):
            shutdown()
