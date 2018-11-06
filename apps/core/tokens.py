from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import salted_hmac
from django.utils.http import int_to_base36


class TokenGenerator(PasswordResetTokenGenerator):

    def _make_token_with_timestamp(self, user, timestamp):
        ts_b36 = int_to_base36(timestamp)
        key_salt = 'apps.core.tokens.TokenGenerator'
        value = (str(user.pk) + user.password + str(timestamp))
        hash = salted_hmac(key_salt, value).hexdigest()[::2]
        return '%s-%s' % (ts_b36, hash)


default_token_generator = TokenGenerator()
