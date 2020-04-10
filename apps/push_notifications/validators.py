import re
from datetime import datetime

from django.utils import timezone
from django.utils.encoding import force_text
from OpenSSL import crypto
from rest_framework.serializers import ValidationError


class APNSCertificateValidator:
    FRIENDLY_NAME_PATTERN = re.compile(r'^Apple (?:(\S+) IOS )?Push Services: (\S+)$', re.I)
    NOT_AFTER_FORMATS = (
        '%Y%m%d%H%M%SZ',
        '%Y%m%d%H%M%S%z'
    )

    def __init__(self, _type):
        self.type = _type

    def __call__(self, value):
        value._certificate_type = None
        value._certificate_bundle = None
        value._certificate_expiration = None

        try:
            pkcs12 = crypto.load_pkcs12(value.read(), '')
            certificate = crypto.dump_certificate(crypto.FILETYPE_PEM, pkcs12.get_certificate())
            x509 = crypto.load_certificate(crypto.FILETYPE_PEM, certificate)
        except Exception:
            raise ValidationError('Invalid file.')

        friendlyname = pkcs12.get_friendlyname()
        not_after = x509.get_notAfter()
        _type, bundle = self.check_friendlyname(friendlyname)
        expiration_date = self.check_expiration_date(not_after)

        # We need this for future validation in serializer class
        value._certificate_type = _type
        value._certificate_bundle = bundle
        value._certificate_expiration = expiration_date
        value.seek(0)

    def check_friendlyname(self, friendlyname):
        if not friendlyname:
            raise ValidationError('Empty friendlyname date.')

        friendlyname = force_text(friendlyname)
        match = self.FRIENDLY_NAME_PATTERN.match(friendlyname)

        if not match:
            raise ValidationError('Invalid friendly name: "{}".'.format(friendlyname))

        _type, bundle = match.groups()

        # if _type is None this cert can be used in both Production
        # and Development environments
        if _type and self.type != _type:
            message = 'Incorrect certificate type. Upload appropriate {} certificate file.'
            raise ValidationError(message.format(self.type.lower()))

        return _type, bundle

    def check_expiration_date(self, not_after):
        if not not_after:
            raise ValidationError('Empty expiration date.')

        not_after = force_text(not_after)
        expiration_date = None
        for _format in self.NOT_AFTER_FORMATS:
            try:
                expiration_date = datetime.strptime(not_after, _format)
            except (ValueError, TypeError):
                pass

        if expiration_date is None:
            message = 'Invalid expiration date: "{}".'
            raise ValidationError(message.format(not_after))

        if expiration_date < timezone.now():
            message = 'Your certificate has expired: "{}".'
            raise ValidationError(message.format(expiration_date))

        return expiration_date
