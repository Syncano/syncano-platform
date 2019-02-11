# coding=UTF8
import os
import re
import socket
import subprocess
from datetime import datetime

import requests
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from dns import resolver
from dns.exception import DNSException
from settings.celeryconf import app, register_task

from apps.core.helpers import Cached
from apps.core.mixins import TaskLockMixin
from apps.core.tasks import InstanceBasedTask
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance

from .exceptions import CNameNotSet, DomainDoesNotExist, HostingDomainException, WrongCName
from .models import Hosting

CERT_SCRIPTS_PATH = '/home/syncano/app/scripts/certs'

ISSUE_SSL_CERT_SCRIPT = os.path.join(CERT_SCRIPTS_PATH, 'issue.sh')
REMOVE_SSL_CERT_SCRIPT = os.path.join(CERT_SCRIPTS_PATH, 'remove.sh')
RENEW_SSL_CERT_SCRIPT = os.path.join(CERT_SCRIPTS_PATH, 'renew.sh')
CERTS_PATH = os.environ.get('CERT_HOME', '/acme/certs')
CERTS_PEM_PATH = os.path.join(CERTS_PATH, 'pem')

REFRESH_SKIP_RETCODE = 2
MAX_DELETION_DAYS = 3
ACME_LOCK_KEY_TEMPLATE = 'lock:acme:{instance_pk}'


@register_task
class HostingAddSecureCustomDomainTask(TaskLockMixin, InstanceBasedTask):
    default_retry_delay = 10
    lock_blocking_timeout = None

    def get_lock_key(self, *args, **kwargs):
        return ACME_LOCK_KEY_TEMPLATE.format(instance_pk=kwargs['instance_pk'])

    def validate_domain(self, domain):
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            raise DomainDoesNotExist()

        try:
            answers = resolver.query(domain, 'CNAME')
        except DNSException:
            # If domain has no CNAME and it's a root domain, check if CNAME flattening is used
            if domain.count('.') == 1:
                try:
                    r = requests.get('http://{}/2a1b7ceb-2b7c-4bd2-a40f-8b021278f5ea/'.format(domain),
                                     timeout=(1.0, 3.0), allow_redirects=False)
                    if r.status_code == requests.codes.ok and r.content.decode() == settings.LOCATION:
                        return
                except requests.RequestException:
                    pass
            raise CNameNotSet()

        if len(answers) != 1:
            raise WrongCName()

        cname = answers[0].target.to_unicode()
        self.validate_cname(cname)

    def validate_cname(self, cname):
        # Check expected CNAME value
        expected_cnames = ['{}.{}{}.'.format(self.instance.name, settings.LOCATION, settings.HOSTING_DOMAIN)]
        if settings.MAIN_LOCATION:
            expected_cnames.append('{}{}.'.format(self.instance.name, settings.HOSTING_DOMAIN))
        for expected_cname in expected_cnames:
            if cname == expected_cname or re.match(r'^[a-z0-9-]+--%s$' % expected_cname, cname):
                return
        raise WrongCName()

    def run(self, hosting_pk, domain, **kwargs):
        hosting_qs = Hosting.objects.filter(pk=hosting_pk)

        try:
            self.validate_domain(domain)
            subprocess.check_output([ISSUE_SSL_CERT_SCRIPT, domain], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            try:
                raise self.retry(exc=exc)
            except MaxRetriesExceededError:
                hosting_qs.update(ssl_status=Hosting.SSL_STATUSES.UNKNOWN)
                self.get_logger().error('Unexpected script error during processing of '
                                        'Hosting[pk=%s] in Instance[pk=%s]: %s',
                                        hosting_pk, self.instance.pk, exc.output, exc_info=1)

        except HostingDomainException as exc:
            hosting_qs.update(ssl_status=exc.status)
        except Exception:
            hosting_qs.update(ssl_status=Hosting.SSL_STATUSES.UNKNOWN)
            self.get_logger().error('Unhandled error during processing of Hosting[pk=%s] in Instance[pk=%s]',
                                    hosting_pk, self.instance.pk, exc_info=1)
        else:
            hosting_qs.update(ssl_status=Hosting.SSL_STATUSES.ON)


@register_task
class HostingRefreshSecureCustomDomainCertTask(TaskLockMixin, app.Task):
    def run(self, **kwargs):
        logger = self.get_logger()

        for domain in os.listdir(CERTS_PATH):
            pem_cert = os.path.join(CERTS_PEM_PATH, '{}.pem'.format(domain))

            # Skip non-domain files/directories
            if domain.startswith('.') or '.' not in domain:
                continue

            # Try to get instance
            try:
                instance = Cached(Instance, kwargs={'domains__contains': [domain]}).get()
            except Instance.DoesNotExist:
                instance = None
                logger.warning('Instance with domain %s no longer exists', domain)

            # If instance does not exist or PEM file is missing - delete the redundant cert files
            if instance is None or not os.path.exists(pem_cert):
                self.remove_domain(logger, domain=domain)
                continue

            try:
                subprocess.check_output([RENEW_SSL_CERT_SCRIPT, domain], stderr=subprocess.STDOUT)
                os.utime(pem_cert, None)
            except subprocess.CalledProcessError as exc:
                # If refresh was skipped, move along
                if exc.returncode == REFRESH_SKIP_RETCODE:
                    os.utime(pem_cert, None)
                    continue

                mtime = os.path.getmtime(pem_cert)
                diff = datetime.now() - datetime.fromtimestamp(mtime)
                logger.warning('Refresh failed for domain "%s" (last success: %s days ago) with output: %s',
                               domain, diff.days, exc.output, exc_info=1)

                if diff.days > MAX_DELETION_DAYS:
                    # Disabling SSL for that domain
                    self.remove_domain(logger, domain=domain, instance=instance)

    @staticmethod
    def remove_domain(logger, domain, instance=None):
        logger.warning('Removing obsolete certs for %s in Instance=%s', domain, instance)

        try:
            subprocess.check_output([REMOVE_SSL_CERT_SCRIPT, domain], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            logger.error('Unexpected script error during removal of '
                         'Hosting domain "%s" in Instance=%s: %s',
                         domain, instance, exc.output, exc_info=1)

        if instance is not None:
            set_current_instance(instance)
            Hosting.objects.filter(domains__contains=[domain]).update(ssl_status=Hosting.SSL_STATUSES.INVALID_DOMAIN)
