import codecs
import os
from datetime import datetime
from ssl import SSLError
from tempfile import NamedTemporaryFile

import pytz
from django.conf import settings
from gcm import GCM
from gcm.gcm import GCMException
from OpenSSL import crypto
from settings.celeryconf import app, register_task

from apps.core.helpers import Cached, iterate_over_queryset_in_chunks
from apps.core.mixins import TaskLockMixin
from apps.core.tasks import InstanceBasedTask
from apps.instances.models import InstanceIndicator

from .apns.exceptions import APNSException, APNSServerError
from .apns.message import APNSMessage as APNSPushMessage
from .apns.sockets import APNSFeedbackSocket, APNSPushSocket
from .models import APNSConfig, APNSDevice, APNSMessage, GCMConfig, GCMDevice, GCMMessage


@register_task
class SendGCMMessage(InstanceBasedTask):
    def run(self, message_pk, **kwargs):
        config = Cached(GCMConfig, kwargs={'id': 1}).get()
        message = GCMMessage.objects.get(pk=message_pk)
        environment = message.content.pop('environment')
        api_key = getattr(config, '{}_api_key'.format(environment))

        status = GCMMessage.STATUSES.ERROR
        try:
            if not api_key:
                raise GCMException('GCM api key for "{}" environment is required.'.format(environment))

            status, result = self.make_request(api_key, message)
        except GCMException as ex:
            result = str(ex)
        except Exception:
            result = 'Internal server error.'
            self.get_logger().error('Unhandled error during processing of GCMMessage[pk=%s] in Instance[pk=%s]',
                                    message_pk, self.instance.pk, exc_info=1)

        GCMMessage.objects.filter(pk=message_pk).update(status=status, result=result)

    def make_request(self, api_key, message):
        gcm = GCM(api_key)
        response = gcm.json_request(**message.content)

        invalid_reg_ids = 0

        # Handling errors
        if 'errors' in response:
            for error, reg_ids in response['errors'].items():
                # Check for errors and act accordingly
                if error in ['NotRegistered', 'InvalidRegistration']:
                    invalid_reg_ids += GCMDevice.objects.filter(registration_id__in=reg_ids).update(is_active=False)

        if 'canonical' in response:
            for reg_id, canonical_id in response['canonical'].items():
                # Replace reg_id with canonical_id
                GCMDevice.objects.filter(registration_id=reg_id).update(registration_id=canonical_id)

        status = GCMMessage.STATUSES.DELIVERED
        if len(message.content['registration_ids']) == invalid_reg_ids:
            status = GCMMessage.STATUSES.ERROR
        elif invalid_reg_ids > 0:
            status = GCMMessage.STATUSES.PARTIALLY_DELIVERED

        return status, response


@register_task
class SendAPNSMessage(InstanceBasedTask):
    def run(self, message_pk, **kwargs):
        config = Cached(APNSConfig, kwargs={'id': 1}).get()
        message = APNSMessage.objects.get(pk=message_pk)
        environment = message.content.pop('environment')
        certificate = getattr(config, '{}_certificate'.format(environment))
        bundle_identifier = getattr(config, '{}_bundle_identifier'.format(environment))

        update_dict = {'status': APNSMessage.STATUSES.ERROR}
        try:
            if not certificate:
                raise APNSException('APNS certificate for "{}" environment is required.'.format(environment))

            if not bundle_identifier:
                raise APNSException('APNS bundle identifier for "{}" environment is required.'.format(environment))

            p12 = crypto.load_pkcs12(str(certificate), '')
            self.make_request(p12, message, environment)
        except APNSServerError as exc:
            update_dict['result'] = {
                'status': exc.status,
                'identifier': exc.identifier,
                'description': exc.description,
            }
        except APNSException as exc:
            update_dict['result'] = str(exc)
        except (SSLError, crypto.Error):
            update_dict['result'] = 'Invalid certificate.'
        except TypeError:
            update_dict['result'] = 'Invalid registration_id value.'
        except Exception:
            update_dict['result'] = 'Internal server error.'
            self.get_logger().error('Unhandled error during processing of APNSMessage[pk=%s] in Instance[pk=%s]',
                                    message_pk, self.instance.pk, exc_info=1)
        else:
            update_dict['status'] = APNSMessage.STATUSES.DELIVERED
        APNSMessage.objects.filter(pk=message_pk).update(**update_dict)

    def make_request(self, p12, message, environment):
        registration_ids = message.content.pop('registration_ids')

        # Looks like Python 2.5 :(
        certfile = NamedTemporaryFile(mode='w', delete=False)
        certfile.write(crypto.dump_certificate(crypto.FILETYPE_PEM, p12.get_certificate()))
        certfile.close()

        keyfile = NamedTemporaryFile(mode='w', delete=False)
        keyfile.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, p12.get_privatekey()))
        keyfile.close()

        try:
            messages = [APNSPushMessage(reg_id, message.content) for reg_id in registration_ids]
            socket = APNSPushSocket(environment, certfile=certfile.name, keyfile=keyfile.name)
            socket.send(messages)
        finally:
            os.unlink(certfile.name)
            os.unlink(keyfile.name)


@register_task
class GetAPNSFeedback(InstanceBasedTask):
    lock_generate_hash = True

    def run(self, environment, **kwargs):
        logger = self.get_logger()
        config = Cached(APNSConfig, kwargs={'id': 1}).get()
        certificate = getattr(config, '{}_certificate'.format(environment))
        bundle_identifier = getattr(config, '{}_bundle_identifier'.format(environment))

        certfile = NamedTemporaryFile(mode='w', delete=False)
        keyfile = NamedTemporaryFile(mode='w', delete=False)

        try:
            if not certificate:
                raise APNSException('APNS certificate for "{}" environment is required.'.format(environment))

            if not bundle_identifier:
                raise APNSException('APNS bundle identifier for "{}" environment is required.'.format(environment))

            p12 = crypto.load_pkcs12(str(certificate), '')

            # Looks like Python 2.5 :(
            certfile.write(crypto.dump_certificate(crypto.FILETYPE_PEM, p12.get_certificate()))
            certfile.close()

            keyfile.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, p12.get_privatekey()))
            keyfile.close()

            socket = APNSFeedbackSocket(environment, certfile=certfile.name, keyfile=keyfile.name)

            for timestamp, token in socket.read():
                created_at = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
                registration_id = codecs.encode(token, 'hex_codec').decode()

                logger.debug('Updating %s %s', timestamp, registration_id)

                APNSDevice.objects.filter(registration_id=registration_id,
                                          created_at__lte=created_at).update(is_active=False)
        except (APNSException, TypeError, SSLError, crypto.Error):
            logger.warning('Error occurred during processing of APNS Feedback in Instance[pk=%s]',
                           self.instance.pk, exc_info=1)
        finally:
            os.unlink(certfile.name)
            os.unlink(keyfile.name)


@register_task
class APNSFeedbackDispatcher(TaskLockMixin, app.Task):

    def run(self):
        logger = self.get_logger()
        logger.debug('Loading instance indicators...')

        qs = InstanceIndicator.objects.filter(type=InstanceIndicator.TYPES.APNS_DEVICES_COUNT,
                                              value__gt=0,
                                              instance__location=settings.LOCATION).select_related('instance')

        for chunk_of_pks in iterate_over_queryset_in_chunks(qs, 'instance_id'):
            logger.debug('Starting tasks for %s instances...', len(chunk_of_pks))

            for instance_pk in chunk_of_pks:
                GetAPNSFeedback.delay('production', instance_pk=instance_pk)
                GetAPNSFeedback.delay('development', instance_pk=instance_pk)
