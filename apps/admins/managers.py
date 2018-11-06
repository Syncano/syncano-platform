# coding=UTF8
from django.contrib.auth.models import BaseUserManager
from django.utils import timezone

from apps.core.managers import LiveManager


class AdminManager(LiveManager, BaseUserManager):
    def create_user(self, email=None, password=None, save=True,
                    is_active=True, **extra_fields):
        """
        Creates and saves a Admin with given email and password.
        """
        now = timezone.now()

        if not email:
            raise ValueError('Email must be set.')

        if 'email' in extra_fields:
            email = extra_fields['email']
        user = self.model(email=email,
                          is_staff=False, is_active=is_active, is_superuser=False,
                          last_login=now, created_at=now, **extra_fields)

        user.set_password(password)

        if save:
            user.save(using=self._db)
        return user

    def create_superuser(self, email=None, password=None, save=True, **extra_fields):
        u = self.create_user(email=email, password=password, save=False, **extra_fields)
        u.is_staff = True
        u.is_active = True
        u.is_superuser = True

        if save:
            u.save(using=self._db)
        return u
